# Amazon Agent 🛒

Amazon Agent is an automation tool built with **Python** and **Selenium** that simulates a shopping assistant on Amazon.  
It can log in with your account, search for products, filter results by price and rating, and optionally add items to the cart.

---

## 🚀 Features
- Automated login using your Amazon credentials.
- Search for any product on Amazon.
- Apply filters like **minimum/maximum price** and **minimum rating**.
- Add top results directly to your cart.
- Easy configuration using environment variables.

---

---

## ⚙️ Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/amazon-agent.git
   cd amazon-agent


2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Copy `.env.example` to `.env` and add your details:

   ```env
   AMAZON_EMAIL=your-email@example.com
   AMAZON_PASSWORD=your-password
   PRODUCT_TO_SEARCH=laptop
   ```

---

## ▶️ Usage

Run the agent:

```bash
python amazon_agent.py
```

You will be prompted to enter:

* Product to search
* Minimum and maximum price
* Minimum rating

The agent will then open Chrome, log in to Amazon, perform the search, and filter results.

---

## 🛠 Requirements

* Python 3.8+
* Google Chrome & ChromeDriver
* Selenium

---

## ⚠️ Disclaimer

This project is for **educational purposes only**. Automating interactions with Amazon may violate their Terms of Service. Use responsibly.
