from flask import Flask, request, jsonify
import requests
import base64
import os

app = Flask(__name__)

# Configuration
SCREENSHOT_API_KEY = os.environ.get('SCREENSHOT_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# The grading prompt for Gemini
GRADING_PROMPT = """You are a brutally honest website and brand auditor for Nexli Automation. Your job is to evaluate business websites against 2026 standards — not 2015 standards.

You grade HARSHLY because:
- We are in a massive wealth transfer. Gen Z and millennials are becoming the decision-makers.
- Modern users expect fast, clean, mobile-first experiences.
- If a website looks outdated, slow, or confusing — trust is gone in 3 seconds.
- "Good enough" websites are invisible websites.

---

## SCORING CATEGORIES (100 POINTS TOTAL)

### 1. FIRST IMPRESSION (20 points)
- Does the homepage immediately communicate what the business does?
- Is there a clear headline and value proposition above the fold?
- Would a 22-year-old trust this site with their money in 3 seconds?
- Does it look like a real company or a side hustle?

### 2. VISUAL DESIGN & BRANDING (20 points)
- Is the logo professional or does it look like a DIY job?
- Are colors consistent throughout the site?
- Is the typography clean and readable?
- Does the overall aesthetic feel modern (2024-2026) or outdated (2010-2018)?
- Is there visual hierarchy that guides the eye?

### 3. MOBILE & SPEED (20 points)
- Does the site appear to be responsive/mobile-friendly based on the layout?
- Is the design clean enough to load fast?
- Are buttons/CTAs likely thumb-friendly on mobile?
- Is text readable without zooming?

### 4. USER EXPERIENCE & NAVIGATION (20 points)
- Can a visitor find what they need in under 10 seconds?
- Is the navigation simple or cluttered?
- Is there a clear CTA (book a call, contact, get started)?
- Are there trust signals (testimonials, reviews, certifications, client logos)?

### 5. LEAD CAPTURE & CONVERSION (20 points)
- Is there an obvious way to contact the business?
- Is there online booking or a contact form visible?
- Is there a lead magnet or reason to engage?
- Would a busy person actually fill out the form or bounce?

---

## OUTPUT FORMAT

Respond with ONLY this format (no extra text before or after):

**WEBSITE AUDIT SCORECARD**

**Overall Score:** [X]/100
**Grade:** [A / B / C / D / F]

---

**CATEGORY BREAKDOWN:**

| Category | Score | Verdict |
|----------|-------|---------|
| First Impression | X/20 | [One-line verdict] |
| Visual Design & Branding | X/20 | [One-line verdict] |
| Mobile & Speed | X/20 | [One-line verdict] |
| User Experience | X/20 | [One-line verdict] |
| Lead Capture | X/20 | [One-line verdict] |

---

**TOP 3 PROBLEMS:**

1. [Biggest issue + why it's costing them clients]
2. [Second issue + why it matters]
3. [Third issue + what it signals to prospects]

---

**BOTTOM LINE:**

[2-3 sentences. Brutally honest summary. Would you trust this business with your money based on this website? What's the one thing they must fix first?]

---

**NEXT STEP:**

Your website should be your hardest-working employee — not your weakest link. Book a free strategy call with Nexli to fix this: https://nexli.net/book

---

## GRADING SCALE

- **90-100 (A):** Excellent. Minor tweaks only. Rare.
- **80-89 (B):** Solid. Some improvements needed but competitive.
- **70-79 (C):** Average. Losing leads to better-looking competitors.
- **60-69 (D):** Below average. Needs significant work. Hurting credibility.
- **0-59 (F):** Failing. This website is actively costing the business money.

Now analyze the website screenshot provided:"""


def take_screenshot(url):
    """Take a screenshot of the website using ScreenshotOne API"""
    
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url
    
    screenshot_url = "https://api.screenshotone.com/take"
    
    params = {
        'access_key': SCREENSHOT_API_KEY,
        'url': url,
        'viewport_width': 1920,
        'viewport_height': 1080,
        'device_scale_factor': 1,
        'format': 'png',
        'full_page': 'false',
        'block_ads': 'true',
        'block_cookie_banners': 'true'
    }
    
    response = requests.get(screenshot_url, params=params)
    
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Screenshot API error: {response.status_code} - {response.text}")


def analyze_with_gemini(screenshot_bytes):
    """Send screenshot to Gemini for analysis using REST API"""
    
    image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": GRADING_PROMPT},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_base64
                    }
                }
            ]
        }]
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    else:
        raise Exception(f"Gemini API error: {response.status_code} - {response.text}")


@app.route('/audit', methods=['POST'])
def audit_website():
    """Main endpoint that GHL will call"""
    
    try:
        data = request.json
        
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        contact_email = data.get('email')
        contact_name = data.get('name')
        
        if not website_url:
            return jsonify({
                'success': False,
                'error': 'No website URL provided'
            }), 400
        
        # Check API keys
        if not SCREENSHOT_API_KEY:
            return jsonify({
                'success': False,
                'error': 'SCREENSHOT_API_KEY not configured'
            }), 500
            
        if not GEMINI_API_KEY:
            return jsonify({
                'success': False,
                'error': 'GEMINI_API_KEY not configured'
            }), 500
        
        # Step 1: Take screenshot
        try:
            screenshot = take_screenshot(website_url)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Screenshot failed: {str(e)}'
            }), 500
        
        # Step 2: Analyze with Gemini
        try:
            scorecard = analyze_with_gemini(screenshot)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Gemini analysis failed: {str(e)}'
            }), 500
        
        return jsonify({
            'success': True,
            'scorecard': scorecard,
            'website_url': website_url,
            'contact_email': contact_email,
            'contact_name': contact_name
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
