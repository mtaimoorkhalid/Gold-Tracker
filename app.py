from flask import Flask, render_template, jsonify
import cloudscraper
from bs4 import BeautifulSoup
import re
from transformers import pipeline

app = Flask(__name__)

# --- 1. INITIALIZE AI MODEL ---
print("🧠 LOADING AI MODEL...")
qa_pipeline = pipeline(
    "question-answering", 
    model="distilbert-base-cased-distilled-squad",
    tokenizer="distilbert-base-cased-distilled-squad"
)
print("✅ AI MODEL READY.")

# --- ANTI-BOT SETUP ---
def get_scraper():
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

def clean_price(text):
    if not text: return 0
    clean = re.sub(r'[^\d]', '', str(text))
    return int(clean) if clean else 0

def smart_ai_search(full_text):
    """Filters text and uses AI to find the latest gold price."""
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    valid_candidates = []

    for sentence in sentences:
        # Optimization: Only process sentences with numbers > 400k
        potential_prices = re.findall(r'([\d,]{6,7})', sentence)
        if not any(400000 < clean_price(p) < 900000 for p in potential_prices):
            continue
        
        result = qa_pipeline(question="What is the gold price?", context=sentence)
        price = clean_price(result['answer'])
        
        if 400000 < price < 900000:
            valid_candidates.append(price)

    return max(valid_candidates) if valid_candidates else None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/rates')
def api_rates():
    found_rates = []
    scraper = get_scraper()

    # --- SOURCE 1: BUSINESS RECORDER ---
    try:
        url = "https://www.brecorder.com/live/gold-rates"
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            price = smart_ai_search(BeautifulSoup(resp.text, 'html.parser').get_text(" ", strip=True))
            if price:
                found_rates.append({"price": price, "price_text": f"{price:,}", "source": "Business Recorder", "url": url})
    except Exception as e: print(f"BR Error: {e}")

    # --- SOURCE 2: DAWN NEWS (RSS) ---
    try:
        rss_url = "https://www.dawn.com/feeds/business"
        resp = scraper.get(rss_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'xml')
        for item in soup.find_all('item')[:5]:
            if "gold" in item.title.text.lower():
                price = smart_ai_search(item.title.text)
                if not price:
                    art_text = BeautifulSoup(scraper.get(item.link.text).text, 'html.parser').get_text(" ", strip=True)
                    price = smart_ai_search(art_text)
                if price:
                    found_rates.append({"price": price, "price_text": f"{price:,}", "source": "Dawn News", "url": item.link.text})
                    break
    except Exception as e: print(f"Dawn Error: {e}")

    # --- SOURCE 3: HAMARIWEB ---
    try:
        url = "https://hamariweb.com/finance/gold_rate/"
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for specific 24K price text
            rate_text = soup.find(string=re.compile(r'Rs\.\s*[\d,]{6}'))
            price = clean_price(rate_text)
            if 400000 < price < 900000:
                found_rates.append({"price": price, "price_text": f"{price:,}", "source": "Hamariweb", "url": url})
    except Exception as e: print(f"Hamariweb Error: {e}")

    if found_rates:
        found_rates.sort(key=lambda x: x['price'], reverse=True)
        return jsonify(found_rates)
    return jsonify({"error": "No data found", "data": []})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
