from flask import Flask, request, jsonify
import requests
import base64
import os
import boto3
from botocore.config import Config
import uuid
from datetime import datetime

app = Flask(__name__)

SCREENSHOT_API_KEY = os.environ.get('SCREENSHOT_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')

GRADING_PROMPT = """You are a brutally honest website and brand auditor. Score this website out of 100 based on:

1. FIRST IMPRESSION (20 pts) - Clear headline, value proposition, trust at first glance
2. VISUAL DESIGN (20 pts) - Logo, colors, typography, modern aesthetic
3. MOBILE & SPEED (20 pts) - Responsive, clean, fast-loading design
4. USER EXPERIENCE (20 pts) - Navigation, clear CTA, trust signals
5. LEAD CAPTURE (20 pts) - Contact options, booking, lead magnets

Be harsh but fair. Return ONLY valid JSON in this exact format:
{
    "overall_score": 65,
    "grade": "D",
    "categories": {
        "first_impression": {"score": 12, "verdict": "One line verdict"},
        "visual_design": {"score": 14, "verdict": "One line verdict"},
        "mobile_speed": {"score": 13, "verdict": "One line verdict"},
        "user_experience": {"score": 15, "verdict": "One line verdict"},
        "lead_capture": {"score": 11, "verdict": "One line verdict"}
    },
    "top_problems": [
        "First major problem and why it costs them clients",
        "Second problem and business impact",
        "Third problem and what it signals"
    ],
    "bottom_line": "2-3 sentence brutally honest summary"
}"""

PDF_PROMPT = """Create a beautiful, professional HTML document for a website audit report. Use this data:

{audit_data}

Website URL: {website_url}
Business Name: {business_name}

Design requirements:
- Use Nexli branding: Primary blue #2563EB, Cyan accent #06B6D4, Dark #0A1628
- Clean, modern design with plenty of white space
- Professional typography (use system fonts)
- Include a header with "NEXLI" branding and "Website Audit Report" title
- Show the overall score prominently with a color indicator (red for F/D, yellow for C, green for B/A)
- Display each category with its score as a progress bar
- List the top 3 problems clearly
- Include the bottom line assessment
- Add a CTA section at the bottom: "Ready to fix these issues? Book a free strategy call: https://nexli.net/book"
- Make it look like a premium consulting deliverable
- Include current date

Return ONLY the complete HTML code, no explanations. Start with <!DOCTYPE html>"""


def take_screenshot(url):
    if not url.startswith('http'):
        url = 'https://' + url
    
    params = {
        'access_key': SCREENSHOT_API_KEY,
        'url': url,
        'viewport_width': 1280,
        'viewport_height': 800,
        'format': 'png',
        'full_page': 'false'
    }
    
    response = requests.get("https://api.screenshotone.com/take", params=params, timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"Screenshot failed: {response.status_code}")
    
    return response.content


def analyze_with_gemini(screenshot_bytes):
    image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": GRADING_PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            ]
        }]
    }
    
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Gemini failed: {response.status_code} - {response.text}")
    
    result = response.json()
    return result['candidates'][0]['content']['parts'][0]['text']


def generate_pdf_html(audit_data, website_url, business_name):
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": PDF_PROMPT.format(
                audit_data=audit_data,
                website_url=website_url,
                business_name=business_name or "the business"
            )
        }]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Claude failed: {response.status_code} - {response.text}")
    
    result = response.json()
    return result['content'][0]['text']


def upload_to_r2(html_content, filename):
    s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4')
    )
    
    s3_client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=filename,
        Body=html_content.encode('utf-8'),
        ContentType='text/html'
    )
    
    public_url = f"{R2_PUBLIC_URL}/{filename}"
    return public_url


@app.route('/audit', methods=['POST'])
def audit_website():
    try:
        data = request.json or {}
        
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        contact_email = data.get('email')
        contact_name = data.get('name')
        
        if not website_url:
            return jsonify({'success': False, 'error': 'No website URL provided'}), 400
        
        screenshot = take_screenshot(website_url)
        
        audit_json = analyze_with_gemini(screenshot)
        
        audit_json = audit_json.strip()
        if audit_json.startswith('```json'):
            audit_json = audit_json[7:]
        if audit_json.startswith('```'):
            audit_json = audit_json[3:]
        if audit_json.endswith('```'):
            audit_json = audit_json[:-3]
        audit_json = audit_json.strip()
        
        html_report = generate_pdf_html(audit_json, website_url, contact_name)
        
        if '```html' in html_report:
            html_report = html_report.split('```html')[1].split('```')[0]
        elif html_report.startswith('```'):
            html_report = html_report[3:]
            if html_report.endswith('```'):
                html_report = html_report[:-3]
        
        filename = f"audit-{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d')}.html"
        report_url = upload_to_r2(html_report, filename)
        
        return jsonify({
            'success': True,
            'report_url': report_url,
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
    return jsonify({
        'status': 'healthy',
        'screenshot_key': bool(SCREENSHOT_API_KEY),
        'gemini_key': bool(GEMINI_API_KEY),
        'claude_key': bool(CLAUDE_API_KEY),
        'r2_configured': bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
