import os
import random
import re
import time
import logging
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- Load Environment Variables ---
load_dotenv()

# --- CONFIG ---
EMAIL = os.getenv("AMAZON_EMAIL")
PASSWORD = os.getenv("AMAZON_PASSWORD")
SEARCH_ITEM = os.getenv("PRODUCT_TO_SEARCH", "laptop")
MAX_PRODUCTS = 2  # Agent can decide how many to add

# --- Interactive prompts (move before launching Chrome to avoid chromedriver/stdout noise) ---
default_search = os.environ.get("PRODUCT_TO_SEARCH", SEARCH_ITEM)
try:
    user_input = input(f"Product to search: ").strip()
except Exception:
    user_input = ""
SEARCH_ITEM = user_input if user_input else default_search

def _parse_int_safe(s):
    if s is None or s == "":
        return None
    s = re.sub(r"[^\d]", "", s)
    try:
        return int(s)
    except Exception:
        return None

def _parse_float_safe(s):
    if s is None or s == "":
        return None
    m = re.search(r"(\d+(\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

try:
    pmin = input("Min price (leave blank for no min): ").strip()
except Exception:
    pmin = ""
PRICE_MIN = _parse_int_safe(pmin)

try:
    pmax = input("Max price (leave blank for no max): ").strip()
except Exception:
    pmax = ""
PRICE_MAX = _parse_int_safe(pmax)

try:
    rmin = input("Minimum rating (e.g. 4.0) (leave blank for no min): ").strip()
except Exception:
    rmin = ""
MIN_RATING = _parse_float_safe(rmin)

print(f"Searching for: {SEARCH_ITEM!r} | price_min={PRICE_MIN} price_max={PRICE_MAX} min_rating={MIN_RATING}")

# --- SETUP DRIVER ---
# Reduce noisy logs so user can type inputs without interference
logging.getLogger("WDM").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.ERROR)
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
# Chrome-specific quieting
options.add_experimental_option('excludeSwitches', ['enable-logging'])
options.add_argument("--log-level=3")
# Install and set up the driver automatically and route chromedriver logs to null
service = ChromeService(ChromeDriverManager().install(), log_path=os.devnull)
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 20)
print("✅ Driver setup complete.")


def click_element_robust(driver, el):
    """Try a sequence of click strategies to handle overlays/JS handlers.
    Returns True on success, False otherwise.
    """
    try:
        # 1) native JS click
        driver.execute_script('arguments[0].click();', el)
        return True
    except Exception:
        pass
    try:
        # 2) ActionChains move+click
        ActionChains(driver).move_to_element(el).pause(0.1).click(el).perform()
        return True
    except Exception:
        pass
    try:
        # 3) Dispatch MouseEvent via JS
        driver.execute_script(
            "var ev = document.createEvent('MouseEvents'); ev.initMouseEvent('click', true, true); arguments[0].dispatchEvent(ev);",
            el,
        )
        return True
    except Exception:
        pass
    try:
        # 4) click nearest clickable ancestor (a, button, input) as fallback
        ancestor = driver.execute_script(
            "var e=arguments[0]; while(e && !e.matches('a,button,input')){e=e.parentElement;} return e;",
            el,
        )
        if ancestor:
            try:
                driver.execute_script('arguments[0].click();', ancestor)
                return True
            except Exception:
                pass
    except Exception:
        pass
    return False

# --- AMAZON LOGIN ---
try:
    driver.get("https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
    wait.until(EC.visibility_of_element_located((By.ID, "ap_email"))).send_keys(EMAIL + Keys.RETURN)
    wait.until(EC.visibility_of_element_located((By.ID, "ap_password"))).send_keys(PASSWORD + Keys.RETURN)
    # Wait for the search bar on the homepage to confirm login is complete
    wait.until(EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
    print("✅ Login successful!")
except Exception as e:
    print(f"❌ Login failed. You might need to solve a CAPTCHA manually. Error: {e}")
    driver.quit()
    exit()

# (Prompts are handled earlier before launching the browser.)

# --- SEARCH PRODUCT ---
search_box = wait.until(EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
search_box.send_keys(SEARCH_ITEM + Keys.RETURN)
print(f"🔍 Searching for '{SEARCH_ITEM}'...")

# Wait for search results to load (target items with a non-empty data-asin)
wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-component-type='s-search-result' and @data-asin]")))

# --- SCRAPE PRODUCTS ---
# Prefer items that have a data-asin attribute (real product results). This is more reliable.
products = driver.find_elements(By.XPATH, "//div[contains(@class,'s-result-item') and normalize-space(@data-asin)!='']")
choices = []

print(f"🔎 Raw search result containers found: {len(products)}")

# Try dismissing common overlays (cookie consent, location) that block the page
try:
    # cookie consent by id (common pattern)
    consent_btns = driver.find_elements(By.ID, "sp-cc-accept")
    if consent_btns:
        try:
            consent_btns[0].click()
            time.sleep(0.5)
        except Exception:
            pass
except Exception:
    pass

try:
    # general dialog close buttons (common patterns)
    dlg_btns = driver.find_elements(By.XPATH, "//button[contains(@class,'a-button-close') or contains(@aria-label,'close')]")
    for b in dlg_btns:
        try:
            b.click()
            time.sleep(0.2)
        except Exception:
            continue
except Exception:
    pass

for product in products:
    try:
        # Use a broader selector for the product link/title
        link_el = product.find_element(By.CSS_SELECTOR, "h2 a")
        title = link_el.text.strip()
        link = link_el.get_attribute("href")

        # Skip obviously empty or sponsored-like entries
        if not title or not link:
            continue

        # Basic metadata (best-effort)
        try:
            price_text = product.find_element(By.CSS_SELECTOR, "span.a-price-whole").text.strip()
        except Exception:
            # some items may have "span.a-offscreen" with formatted price
            try:
                price_text = product.find_element(By.CSS_SELECTOR, "span.a-offscreen").text.strip()
            except Exception:
                price_text = "N/A"

        try:
            rating_text = product.find_element(By.CSS_SELECTOR, "span.a-icon-alt").get_attribute("innerHTML").strip()
        except Exception:
            rating_text = "N/A"

        # parse numeric values for filtering
        price_num = None
        if price_text and price_text != "N/A":
            # remove non digits, keep decimals if any
            cleaned = re.sub(r"[^\d.]", "", price_text)
            try:
                # often price is integer rupees; cast to int if no dot, else float
                price_num = int(cleaned) if cleaned and "." not in cleaned else float(cleaned)
            except Exception:
                price_num = None

        rating_num = None
        if rating_text and rating_text != "N/A":
            rating_num = _parse_float_safe(rating_text)

        # Apply user filters (if provided)
        if PRICE_MIN is not None:
            if price_num is None or price_num < PRICE_MIN:
                continue
        if PRICE_MAX is not None:
            if price_num is None or price_num > PRICE_MAX:
                continue
        if MIN_RATING is not None:
            if rating_num is None or rating_num < MIN_RATING:
                continue

        choices.append({"title": title, "price": price_text, "rating": rating_text, "url": link})
    except Exception:
        # skip entries we couldn't parse
        continue

print(f"📦 Found {len(choices)} parsed products on the first page.")
if len(choices) == 0 and len(products) > 0:
    # helpful debug: dump first product HTML snippet to help diagnose DOM mismatch
    try:
        first_html = products[0].get_attribute('outerHTML')
        print("⚠️ No parsed products. Sample first result HTML (truncated):\n", first_html[:1000])
    except Exception:
        pass
if len(products) > 0:
    with open('sample_product.html','w', encoding='utf-8') as f:
        f.write(products[0].get_attribute('outerHTML'))
    print('Saved sample_product.html – open it in your browser to inspect the DOM')

# --- AGENT DECISION & ADD DIRECTLY FROM SEARCH RESULTS ---
# Attempt to click the "Add to cart" button directly inside each search-result container.
added = []
print("🤖 Agent will try to add up to", MAX_PRODUCTS, "items directly from the search results...")
for product in products:
    if len(added) >= MAX_PRODUCTS:
        break
    try:
        # Best-effort title for logging
        try:
            title_el = product.find_element(By.CSS_SELECTOR, "h2 a")
            title = title_el.text.strip()
        except Exception:
            title = product.get_attribute('data-asin') or 'Unknown product'

        # Scroll product into view so buttons are clickable
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", product)
        time.sleep(0.4)

        # Scoped detection tailored for the markup you shared (data-csa-c-content-id and data-csa-c-item-id)
        btn = None
        try:
            asin = product.get_attribute('data-asin') or ''
        except Exception:
            asin = ''

        # 1) Exact match: div[action] with matching data-csa-c-item-id == product ASIN -> button[name='submit.addToCart']
        if asin:
            try:
                xpath = f".//div[@data-csa-c-content-id='s-search-add-to-cart-action' and @data-csa-c-item-id='{asin}']//button[@name='submit.addToCart']"
                btn = product.find_element(By.XPATH, xpath)
            except Exception:
                btn = None

        # 2) Any add-to-cart action inside the product container
        if not btn:
            try:
                btn = product.find_element(By.XPATH, ".//div[@data-csa-c-content-id='s-search-add-to-cart-action']//button[@name='submit.addToCart']")
            except Exception:
                btn = None

        # 3) Generic button by name inside product container
        if not btn:
            try:
                btn = product.find_element(By.XPATH, ".//button[@name='submit.addToCart']")
            except Exception:
                btn = None

        # 4) Fallback: older or alternate markup (text-based or input)
        if not btn:
            inline_selectors = [
                (By.XPATH, ".//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart') or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]") ,
                (By.XPATH, ".//button[.//span[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]]"),
                (By.XPATH, ".//a[.//span[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]]"),
                (By.CSS_SELECTOR, "input[name='submit.add-to-cart'], button.a-button, .a-button input")
            ]
            for sel in inline_selectors:
                try:
                    cand = product.find_element(sel[0], sel[1])
                    if cand and cand.is_displayed():
                        btn = cand
                        break
                except Exception:
                    continue

        if not btn:
            print(f"⚠️ Inline Add button not found for: {title}")
            continue

        # Try to get previous cart count (if available)
        try:
            prev_count = int(driver.find_element(By.ID, 'nav-cart-count').text.strip())
        except Exception:
            prev_count = None

        # Click via JS to avoid overlay issues
        try:
            driver.execute_script('arguments[0].click();', btn)
        except Exception:
            try:
                btn.click()
            except Exception as e:
                print(f"⚠️ Failed to click add for {title}: {e}")
                continue

        # Wait briefly for confirmation: cart count change or "Added to Cart" text
        added_ok = False
        start = time.time()
        while time.time() - start < 12:
            try:
                if prev_count is not None:
                    cur = int(driver.find_element(By.ID, 'nav-cart-count').text.strip())
                    if cur > prev_count:
                        added_ok = True
                        break
            except Exception:
                pass
            try:
                # generic confirmation text
                conf = driver.find_elements(By.XPATH, "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'added to cart') or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'added to your cart')]")
                if len(conf) > 0:
                    added_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if added_ok:
            print(f"✅ Added to cart: {title}")
            added.append({'title': title})
        else:
            print(f"⚠️ Clicked Add for {title} but no confirmation observed.")

        time.sleep(0.6)
    except Exception as e:
        print(f"⚠️ Error while trying inline add: {e}")
        continue

# If nothing was added inline, fall back to opening product pages and using the more robust add flow
if len(added) == 0:
    print("⚠️ No items added from inline buttons; falling back to opening product pages to add items.")
    # Before opening product pages, attempt a global diagnostic + mapped-click fallback.
    try:
        print("🔍 Running diagnostic: scanning the whole page for 'Add to cart' elements and mapping to ASINs...")
        matches = driver.find_elements(By.XPATH, "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]")
        print(f"Diagnostic: found {len(matches)} elements containing 'add to cart' text (case-insensitive).")
        dump_parts = []
        mapped = []
        for idx, el in enumerate(matches, start=1):
            try:
                outer = el.get_attribute('outerHTML') or ''
            except Exception:
                outer = '<no-outerHTML>'
            # find nearest ancestor product container (data-asin)
            asin = None
            try:
                anc = el.find_element(By.XPATH, "ancestor::div[contains(@class,'s-result-item') and normalize-space(@data-asin)!='']")
                asin = anc.get_attribute('data-asin')
            except Exception:
                try:
                    anc = el.find_element(By.XPATH, "ancestor::*[@data-asin]")
                    asin = anc.get_attribute('data-asin')
                except Exception:
                    asin = None
            mapped.append({'index': idx, 'asin': asin or 'N/A', 'html': outer})
            dump_parts.append(f"--- Match {idx} ASIN={asin or 'N/A'} ---\n{outer}\n\n")

        with open('diagnostic_add_button_dump.html', 'w', encoding='utf-8') as f:
            f.write('<html><body>')
            for p in dump_parts:
                f.write(p)
            f.write('</body></html>')
        print("Diagnostic saved to diagnostic_add_button_dump.html")

        # Visual mapping: compute bounding boxes for products and candidate add-buttons,
        # map each candidate to the nearest product whose rect contains the candidate center
        try:
            # gather product rects (only use products with data-asin)
            product_boxes = []
            for p in products:
                try:
                    asin = p.get_attribute('data-asin') or ''
                    rect = driver.execute_script(
                        "var r = arguments[0].getBoundingClientRect(); return {left:r.left,top:r.top,width:r.width,height:r.height,cx:r.left + r.width/2, cy:r.top + r.height/2};",
                        p,
                    )
                    product_boxes.append({'asin': asin, 'elem': p, 'rect': rect})
                except Exception:
                    continue

            # gather candidate add-button elements and rects
            cand_els = driver.find_elements(By.XPATH, "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]")
            candidates = []
            for c in cand_els:
                try:
                    rect = driver.execute_script(
                        "var r = arguments[0].getBoundingClientRect(); return {left:r.left,top:r.top,width:r.width,height:r.height,cx:r.left + r.width/2, cy:r.top + r.height/2};",
                        c,
                    )
                    candidates.append({'el': c, 'rect': rect})
                except Exception:
                    continue

            # map candidates to products
            mapped_by_asin = {}
            for cand in candidates:
                cx = cand['rect']['cx']
                cy = cand['rect']['cy']
                chosen = None
                # first try containment
                for pb in product_boxes:
                    r = pb['rect']
                    if cx >= r['left'] and cx <= r['left'] + r['width'] and cy >= r['top'] and cy <= r['top'] + r['height']:
                        chosen = pb
                        break
                # if none contains, pick nearest by center distance
                if not chosen and len(product_boxes) > 0:
                    best = None
                    best_d = None
                    for pb in product_boxes:
                        pcx = pb['rect']['cx']
                        pcy = pb['rect']['cy']
                        d = (pcx - cx) ** 2 + (pcy - cy) ** 2
                        if best is None or d < best_d:
                            best = pb
                            best_d = d
                    chosen = best

                asin_key = chosen['asin'] if chosen else 'N/A'
                mapped_by_asin.setdefault(asin_key, []).append(cand['el'])

            # prepare parsed_asins (from product URLs or data-asin)
            parsed_asins = set()
            for p in choices:
                url = p.get('url','')
                if '/dp/' in url:
                    parsed_asins.add(url.split('/dp/')[-1].split('/')[0])
            # also include product_boxes as fallback
            for pb in product_boxes:
                if pb['asin']:
                    parsed_asins.add(pb['asin'])

            # click mapped candidates for parsed asins (or any if parsed_asins empty)
            clicks = 0
            for asin, els in mapped_by_asin.items():
                if clicks >= MAX_PRODUCTS:
                    break
                if len(parsed_asins) > 0 and asin not in parsed_asins:
                    continue
                for el in els:
                    if clicks >= MAX_PRODUCTS:
                        break
                    try:
                        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                        time.sleep(0.25)
                        driver.execute_script('arguments[0].click();', el)
                        clicks += 1
                        print(f"🔘 Clicked visually-mapped add element for ASIN={asin}")
                        time.sleep(1.0)
                    except Exception as e:
                        print(f"⚠️ Failed visual click for ASIN={asin}: {e}")
                        continue

            if clicks > 0:
                print(f"✅ Clicked {clicks} visually-mapped add-button(s) from diagnostic scan.")
                time.sleep(2)
                try:
                    cnt = driver.find_element(By.ID, 'nav-cart-count').text.strip()
                    print('Cart count after diagnostic clicks:', cnt)
                except Exception:
                    pass
            else:
                print('⚠️ Diagnostic scan mapped candidates but clicked 0 items.')
        except Exception as e:
            print('⚠️ Visual-mapping diagnostic failed:', e)
    except Exception as e:
        print('⚠️ Diagnostic step failed:', e)

    # If diagnostic clicks didn't add items, fall back to product page flow
    selected = random.sample(choices, min(MAX_PRODUCTS, len(choices))) if len(choices) > 0 else []
    main_window = driver.current_window_handle
    for item in selected:
        driver.switch_to.new_window('tab')
        driver.get(item['url'])
        try:
            # reuse existing robust add-button logic (localized selectors)
            add_btn_selectors = [
                (By.ID, "add-to-cart-button"),
                (By.NAME, "submit.add-to-cart"),
                (By.XPATH, "//input[@id='add-to-cart-button']"),
                (By.XPATH, "//button[contains(., 'Add to Cart') or contains(., 'Add to basket')]")
            ]

            add_btn = None
            for sel in add_btn_selectors:
                try:
                    add_btn = wait.until(EC.element_to_be_clickable(sel))
                    break
                except Exception:
                    continue

            # try simple variation picks
            try:
                variation = driver.find_elements(By.CSS_SELECTOR, "div#variation_size_name, div#variation_color_name, select#native_dropdown_selected_size_name")
                if variation:
                    for v in variation:
                        try:
                            opt = v.find_element(By.CSS_SELECTOR, "li, option, img")
                            opt.click()
                            time.sleep(0.5)
                            break
                        except Exception:
                            continue
            except Exception:
                pass

            if not add_btn:
                raise Exception("Add-to-cart button not found by known selectors")

            try:
                prev_count = int(driver.find_element(By.ID, 'nav-cart-count').text.strip())
            except Exception:
                prev_count = None

            add_btn.click()

            def _added_confirmation(driver_obj):
                try:
                    elems = driver_obj.find_elements(By.XPATH, "//*[contains(text(), 'Added to Cart') or contains(text(), 'Added to your cart')]")
                    if len(elems) > 0:
                        return True
                except Exception:
                    pass
                try:
                    count = driver_obj.find_element(By.ID, 'nav-cart-count').text.strip()
                    return prev_count is None or int(count) != prev_count
                except Exception:
                    return False

            wait.until(_added_confirmation)
            print(f"✅ Added to cart (product page): {item['title']}")
        except Exception as e:
            print(f"⚠️ Could not add (product page): {item['title']}. Reason: {e}")
        finally:
            driver.close()
            driver.switch_to.window(main_window)
            time.sleep(1)

# --- PROCEED TO CART ---
driver.get("https://www.amazon.in/gp/cart/view.html?ref_=nav_cart")
print("🛒 Navigated to cart page.")

# --- PROCEED TO CHECKOUT ---
try:
    # Try multiple selectors because different locales/layouts use different controls/text
    proceed_selectors = [
        (By.NAME, "proceedToRetailCheckout"),
        (By.ID, "sc-buy-box-ptc-button"),
        (By.XPATH, "//input[contains(@value,'Proceed to Buy') or contains(@value,'Proceed to checkout')]") ,
        (By.XPATH, "//a[contains(., 'Proceed to Buy') or contains(., 'Proceed to checkout') or contains(., 'Proceed to buy')]") ,
        (By.XPATH, "//button[contains(., 'Proceed to Buy') or contains(., 'Proceed to checkout') or contains(., 'Proceed to buy')]")
    ]

    clicked = False
    for sel in proceed_selectors:
        try:
            btn = wait.until(EC.element_to_be_clickable(sel))
            btn.click()
            clicked = True
            print("🚀 Clicked proceed button using selector:", sel)
            break
        except Exception:
            continue

    if not clicked:
        print("⚠️ Checkout/Proceed button not found by known selectors. Please check the cart page manually.")
    else:
        # Wait for checkout page or order flow to load (stop before payment)
        def _checkout_loaded(d):
            try:
                url = d.current_url.lower()
                if 'checkout' in url or '/gp/buy' in url or '/checkout' in url:
                    return True
            except Exception:
                pass
            # common checkout elements
            try:
                if len(d.find_elements(By.ID, 'shippingOptionFormId')) > 0:
                    return True
            except Exception:
                pass
            try:
                if len(d.find_elements(By.NAME, 'placeYourOrder1')) > 0:
                    return True
            except Exception:
                pass
            return False

        try:
            wait.until(_checkout_loaded)
            print("✅ Reached checkout page (stopping before payment).")
            try:
                # Show a browser alert so the user is notified inside the browser UI
                msg = (
                    "Please enter your payment details to complete the purchase."
                )
                driver.execute_script("alert(arguments[0]);", msg)
                # Wait for the user to dismiss the alert. Use expected_conditions until_not as primary.
                try:
                    wait.until_not(EC.alert_is_present())
                except Exception:
                    # Fallback: poll for alert absence for up to 5 minutes
                    start = time.time()
                    while time.time() - start < 300:
                        try:
                            # if this raises, alert is gone
                            _ = driver.switch_to.alert
                            time.sleep(0.5)
                        except Exception:
                            break
            except Exception:
                # If JS alerts are blocked or any other error, continue and leave browser open
                pass
        except Exception:
            print("⚠️ Proceed clicked but checkout page not detected within timeout; verify manually.")
except Exception as e:
    print("⚠️ Error while attempting to proceed to buy:", e)

print("Automation finished. Keeping browser open for 60 seconds for inspection.")
time.sleep(60)
driver.quit()