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
    clean = re.sub(r'[^\d]', '', text)
    return int(clean) if clean else 0

def smart_ai_search(full_text):
    """
    Scans text for gold prices. Returns the highest valid price found.
    """
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    valid_candidates = []

    for sentence in sentences:
        potential_prices = re.findall(r'([\d,]{6,7})', sentence)
        if not any(400000 < clean_price(p) < 900000 for p in potential_prices):
            continue
        
        result = qa_pipeline(question="What is the gold price?", context=sentence)
        price = clean_price(result['answer'])
        
        if 400000 < price < 900000:
            valid_candidates.append(price)

    if valid_candidates:
        return max(valid_candidates)

    return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/rates')
def api_rates():
    found_rates = []
    print("\n⚡ STARTING DEEP SCRAPE...")
    scraper = get_scraper()

    # =================================================================
    # SOURCE 1: BUSINESS RECORDER
    # =================================================================
    try:
        url = "https://www.brecorder.com/live/gold-rates"
        print(f"   > [BR] Checking: {url}")
        
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text(" ", strip=True)
            
            price = smart_ai_search(text)
            if price:
                print(f"     ✅ [BR] Found: {price}")
                found_rates.append({
                    "price": price,
                    "price_text": f"{price:,}",
                    "source": "Business Recorder",
                    "url": url
                })
    except Exception as e:
        print(f"     ❌ [BR] Error: {e}")

    # =================================================================
    # SOURCE 2: DAWN NEWS (DEEP SEARCH)
    # =================================================================
    try:
        rss_url = "https://www.dawn.com/feeds/business"
        print(f"   > [DAWN] Checking RSS (Top 10)...")
        
        resp = scraper.get(rss_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'xml')
        
        items = soup.find_all('item')
        # INCREASED RANGE: Check top 10 instead of 3
        for item in items[:10]: 
            title = item.title.text
            link = item.link.text
            
            if "gold" in title.lower():
                print(f"     -> Analyzing: {title[:50]}...")
                
                # Check Headline
                price = smart_ai_search(title)
                
                # Check Body if not in headline
                if not price:
                    print(f"        (Reading Article Body...)")
                    article_resp = scraper.get(link, timeout=15)
                    article_soup = BeautifulSoup(article_resp.text, 'html.parser')
                    article_text = article_soup.get_text(" ", strip=True)
                    price = smart_ai_search(article_text)
                
                if price:
                    print(f"     ✅ [DAWN] Found: {price}")
                    found_rates.append({
                        "price": price,
                        "price_text": f"{price:,}",
                        "source": "Dawn News",
                        "url": link
                    })
                    break # Stop after finding the latest gold story

    except Exception as e:
        print(f"     ❌ [DAWN] Error: {e}")

    # Sort results so the HIGHEST price is always first
    if found_rates:
        found_rates.sort(key=lambda x: x['price'], reverse=True)
        return jsonify(found_rates)
        
    return jsonify({"error": "No data found", "data": []})

@app.route('/api/news')
def api_news():
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, port=5000)