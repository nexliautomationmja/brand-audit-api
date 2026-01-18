from flask import Flask, request, jsonify
import requests
import base64
import os
import boto3
from botocore.config import Config
import uuid
from datetime import datetime
import threading
import json

app = Flask(__name__)

# API Keys
SCREENSHOT_API_KEY = os.environ.get('SCREENSHOT_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

# R2 Config
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')

# GHL Webhook URL for sending results back
GHL_WEBHOOK_URL = os.environ.get('GHL_WEBHOOK_URL')

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
- Add a CTA section at the bottom: "Ready to fix these issues? Book a free strategy call at nexli.net"
- Make it print-friendly
- Return ONLY the HTML, no markdown code fences"""


def take_screenshot(url):
    """Take screenshot using ScreenshotOne API"""
    api_url = "https://api.screenshotone.com/take"
    params = {
        "access_key": SCREENSHOT_API_KEY,
        "url": url,
        "full_page": "false",
        "viewport_width": "1280",
        "viewport_height": "800",
        "device_scale_factor": "1",
        "format": "jpg",
        "image_quality": "80"
    }
    
    response = requests.get(api_url, params=params, timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"Screenshot failed: {response.status_code}")
    
    return base64.b64encode(response.content).decode('utf-8')


def analyze_with_gemini(screenshot_base64):
    """Analyze screenshot with Gemini Vision"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": GRADING_PROMPT},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": screenshot_base64
                    }
                }
            ]
        }]
    }
    
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Gemini failed: {response.status_code} - {response.text}")
    
    result = response.json()
    return result['candidates'][0]['content']['parts'][0]['text']


def generate_pdf_html(audit_data, website_url, business_name):
    """Generate branded HTML report using Claude"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
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
    """Upload HTML report to Cloudflare R2"""
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


def send_to_ghl(contact_id, contact_email, contact_name, website_url, report_url, audit_data, success=True, error=None):
    """Send results back to GHL via webhook"""
    if not GHL_WEBHOOK_URL:
        print("Warning: GHL_WEBHOOK_URL not configured, skipping callback")
        return
    
    payload = {
        "contact_id": contact_id,
        "contact_email": contact_email,
        "contact_name": contact_name,
        "website_url": website_url,
        "success": success,
        "report_url": report_url,
        "audit_data": audit_data,
        "error": error,
        "processed_at": datetime.now().isoformat()
    }
    
    try:
        response = requests.post(GHL_WEBHOOK_URL, json=payload, timeout=30)
        print(f"GHL callback response: {response.status_code}")
    except Exception as e:
        print(f"Failed to send to GHL: {str(e)}")


def process_audit_async(contact_id, contact_email, contact_name, website_url):
    """Background task to process the audit"""
    report_url = None
    audit_data = None
    
    try:
        print(f"Starting audit for {website_url}")
        
        # Step 1: Screenshot
        print("Taking screenshot...")
        screenshot = take_screenshot(website_url)
        
        # Step 2: Gemini analysis
        print("Analyzing with Gemini...")
        audit_json = analyze_with_gemini(screenshot)
        
        # Clean up JSON
        audit_json = audit_json.strip()
        if audit_json.startswith('```json'):
            audit_json = audit_json[7:]
        elif audit_json.startswith('```'):
            audit_json = audit_json.split('\n', 1)[1] if '\n' in audit_json else audit_json[3:]
        if audit_json.endswith('```'):
            audit_json = audit_json.rsplit('```', 1)[0]
        audit_json = audit_json.strip()
        
        # Parse to validate JSON
        audit_data = json.loads(audit_json)
        
        # Step 3: Generate branded HTML report with Claude
        print("Generating HTML report...")
        html_report = generate_pdf_html(audit_json, website_url, contact_name)
        
        # Clean up HTML if needed
        if '```html' in html_report:
            html_report = html_report.split('```html')[1].split('```')[0]
        elif '```' in html_report:
            parts = html_report.split('```')
            if len(parts) >= 2:
                html_report = parts[1]
        
        # Step 4: Upload to R2
        print("Uploading to R2...")
        filename = f"audit-{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d')}.html"
        report_url = upload_to_r2(html_report, filename)
        
        print(f"Audit complete! Report: {report_url}")
        
        # Step 5: Send results back to GHL
        send_to_ghl(
            contact_id=contact_id,
            contact_email=contact_email,
            contact_name=contact_name,
            website_url=website_url,
            report_url=report_url,
            audit_data=audit_data,
            success=True
        )
        
    except Exception as e:
        print(f"Audit failed: {str(e)}")
        send_to_ghl(
            contact_id=contact_id,
            contact_email=contact_email,
            contact_name=contact_name,
            website_url=website_url,
            report_url=None,
            audit_data=None,
            success=False,
            error=str(e)
        )


@app.route('/audit', methods=['POST'])
def audit_website():
    """
    Receive webhook from GHL, immediately return 200, process in background.
    """
    try:
        data = request.json or {}
        
        # Extract fields (support multiple field names)
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        contact_email = data.get('email')
        contact_name = data.get('name')
        contact_id = data.get('id') or data.get('contact_id')
        
        if not website_url:
            return jsonify({'success': False, 'error': 'No website URL provided'}), 400
        
        # Start background processing
        thread = threading.Thread(
            target=process_audit_async,
            args=(contact_id, contact_email, contact_name, website_url)
        )
        thread.daemon = True
        thread.start()
        
        # Immediately return success
        return jsonify({
            'success': True,
            'message': 'Audit started - results will be sent to webhook when complete',
            'website_url': website_url,
            'contact_id': contact_id
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
        'version': '2.0-async',
        'screenshot_key': bool(SCREENSHOT_API_KEY),
        'gemini_key': bool(GEMINI_API_KEY),
        'claude_key': bool(CLAUDE_API_KEY),
        'r2_configured': bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY),
        'ghl_webhook': bool(GHL_WEBHOOK_URL)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
