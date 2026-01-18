from flask import Flask, request, jsonify
import requests
import base64
import os
import traceback

app = Flask(__name__)

SCREENSHOT_API_KEY = os.environ.get('SCREENSHOT_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

GRADING_PROMPT = """You are a brutally honest website and brand auditor. Score this website out of 100 and provide a brief analysis. Be harsh but fair. Format your response as:

**Score:** X/100
**Grade:** A/B/C/D/F

**Summary:** 2-3 sentences about the website.

**Top 3 Issues:**
1. Issue one
2. Issue two  
3. Issue three

**Recommendation:** Book a call with Nexli to fix this: https://nexli.net/book"""


@app.route('/audit', methods=['POST'])
def audit_website():
    try:
        data = request.json or {}
        
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        
        if not website_url:
            return jsonify({'success': False, 'error': 'No website URL provided', 'received_data': data}), 400
        
        if not SCREENSHOT_API_KEY:
            return jsonify({'success': False, 'error': 'SCREENSHOT_API_KEY not set'}), 500
            
        if not GEMINI_API_KEY:
            return jsonify({'success': False, 'error': 'GEMINI_API_KEY not set'}), 500
        
        # Step 1: Screenshot
        if not website_url.startswith('http'):
            website_url = 'https://' + website_url
            
        screenshot_params = {
            'access_key': SCREENSHOT_API_KEY,
            'url': website_url,
            'viewport_width': 1280,
            'viewport_height': 800,
            'format': 'png',
            'full_page': 'false'
        }
        
        screenshot_response = requests.get("https://api.screenshotone.com/take", params=screenshot_params, timeout=30)
        
        if screenshot_response.status_code != 200:
            return jsonify({
                'success': False, 
                'error': f'Screenshot failed: {screenshot_response.status_code}',
                'details': screenshot_response.text[:500]
            }), 500
        
        screenshot_base64 = base64.b64encode(screenshot_response.content).decode('utf-8')
        
        # Step 2: Gemini
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        gemini_payload = {
            "contents": [{
                "parts": [
                    {"text": GRADING_PROMPT},
                    {"inline_data": {"mime_type": "image/png", "data": screenshot_base64}}
                ]
            }]
        }
        
        gemini_response = requests.post(gemini_url, json=gemini_payload, headers={"Content-Type": "application/json"}, timeout=60)
        
        if gemini_response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'Gemini failed: {gemini_response.status_code}',
                'details': gemini_response.text[:500]
            }), 500
        
        result = gemini_response.json()
        scorecard = result['candidates'][0]['content']['parts'][0]['text']
        
        return jsonify({
            'success': True,
            'scorecard': scorecard,
            'website_url': website_url
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'screenshot_key_set': bool(SCREENSHOT_API_KEY),
        'gemini_key_set': bool(GEMINI_API_KEY)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
