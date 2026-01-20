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
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

# R2 Config
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')

# GHL Webhook URL for sending results back
GHL_WEBHOOK_URL = os.environ.get('GHL_WEBHOOK_URL')


def get_grading_prompt(firm_type=None):
    """Get the appropriate grading prompt based on firm type"""
    
    base_prompt = """You are a brutally honest website and brand auditor for financial professionals. Score this website out of 100 based on:

1. FIRST IMPRESSION (20 pts) - Clear headline, value proposition, trust at first glance
2. VISUAL DESIGN (20 pts) - Logo, colors, typography, modern aesthetic  
3. MOBILE & SPEED (20 pts) - Responsive, clean, fast-loading design
4. USER EXPERIENCE (20 pts) - Navigation, clear CTA, trust signals
5. LEAD CAPTURE (20 pts) - Contact options, booking, lead magnets"""

    if firm_type == "CPA Firm":
        base_prompt += """

IMPORTANT: This is a CPA FIRM website. Apply these industry-specific criteria:
- Tax/accounting services should be clearly listed
- Credentials (CPA, EA) should be prominently displayed
- Client portal access is expected
- Tax deadline reminders or resources add value
- Trust signals like BBB, professional associations matter
- Testimonials from business clients are valuable"""

    elif firm_type == "Wealth Management":
        base_prompt += """

IMPORTANT: This is a WEALTH MANAGEMENT firm website. Apply these industry-specific criteria:
- Investment philosophy should be clear
- AUM or client minimums help qualify visitors
- Fiduciary status should be prominently stated
- SEC/FINRA disclosures must be present
- Team credentials (CFP, CFA) should be visible
- Client success stories or case studies add credibility"""

    elif firm_type == "Financial Advisor":
        base_prompt += """

IMPORTANT: This is a FINANCIAL ADVISOR website. Apply these industry-specific criteria:
- Services offered should be clearly defined
- Fee structure transparency is valuable
- Credentials (CFP, ChFC) should be displayed
- Target client type should be evident
- Compliance disclosures are required
- Personal brand/story helps build trust"""

    base_prompt += """

Be harsh but fair. A score of 70+ should be RARE and only for truly excellent sites.
Most financial professional websites should score between 45-65.

Return ONLY valid JSON in this exact format:
{
    "overall_score": 58,
    "grade": "D+",
    "categories": {
        "first_impression": {"score": 12, "verdict": "One line verdict"},
        "visual_design": {"score": 11, "verdict": "One line verdict"},
        "mobile_speed": {"score": 13, "verdict": "One line verdict"},
        "user_experience": {"score": 12, "verdict": "One line verdict"},
        "lead_capture": {"score": 10, "verdict": "One line verdict"}
    },
    "top_problems": [
        "First major problem and why it costs them clients",
        "Second problem and business impact",
        "Third problem and what it signals"
    ],
    "summary": "One sentence summary of the site's main weakness",
    "bottom_line": "2-3 sentence brutally honest summary"
}"""
    
    return base_prompt


PDF_PROMPT = """Create a beautiful, professional HTML document for a website audit report.

The document should:
1. Use the Nexli brand colors (blue gradient: #2563EB to #06B6D4)
2. Have a clean, modern design with plenty of white space
3. Include the Nexli logo at the top (use text "NEXLI" styled as a logo)
4. Display the overall score prominently with a circular progress indicator
5. Show each category with its score and verdict
6. List the top problems clearly
7. Include the bottom line assessment
8. Have a call-to-action button at the bottom linking to https://www.nexli.net/#book

Use inline CSS for all styling. Make it look premium and professional.

Here is the audit data:
{audit_data}

Website analyzed: {website_url}
Client name: {business_name}
Assessment date: {assessment_date}

Return ONLY the complete HTML document, no markdown code blocks."""


def take_screenshot(url):
    """Take a screenshot using ScreenshotOne API"""
    api_url = "https://api.screenshotone.com/take"
    
    params = {
        "access_key": SCREENSHOT_API_KEY,
        "url": url,
        "viewport_width": 1280,
        "viewport_height": 800,
        "device_scale_factor": 1,
        "format": "jpg",
        "image_quality": 80,
        "block_ads": True,
        "block_cookie_banners": True,
        "full_page": False
    }
    
    response = requests.get(api_url, params=params, timeout=60)
    
    if response.status_code == 200:
        return base64.b64encode(response.content).decode('utf-8')
    else:
        raise Exception(f"Screenshot failed: {response.status_code} - {response.text}")


def analyze_with_claude(screenshot_base64, firm_type=None):
    """Analyze screenshot with Claude Vision API"""
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2048,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": screenshot_base64
                    }
                },
                {
                    "type": "text",
                    "text": get_grading_prompt(firm_type)
                }
            ]
        }]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=90)
    
    if response.status_code != 200:
        raise Exception(f"Claude failed: {response.status_code} - {response.text}")
    
    result = response.json()
    return result['content'][0]['text']


def generate_html_report(audit_data, website_url, business_name=None):
    """Generate branded HTML report using Claude"""
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    
    # Get current date for the assessment
    assessment_date = datetime.now().strftime("%B %d, %Y")
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": PDF_PROMPT.format(
                audit_data=audit_data,
                website_url=website_url,
                business_name=business_name or "the business",
                assessment_date=assessment_date
            )
        }]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=90)
    
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


def process_audit_async(contact_id, contact_email, contact_name, website_url, firm_type=None):
    """Background task to process the audit"""
    report_url = None
    audit_data = None
    
    try:
        print(f"Starting audit for {website_url} (firm type: {firm_type or 'default'})")
        
        # Step 1: Screenshot
        print("Taking screenshot...")
        screenshot = take_screenshot(website_url)
        
        # Step 2: Claude analysis (instead of Gemini)
        print("Analyzing with Claude...")
        audit_json = analyze_with_claude(screenshot, firm_type)
        
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
        html_report = generate_html_report(audit_json, website_url, contact_name)
        
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
        data = request.json
        
        # Extract fields (handle various field names)
        contact_id = data.get('id') or data.get('contact_id') or data.get('contactId')
        contact_email = data.get('email') or data.get('contact_email')
        contact_name = data.get('name') or data.get('contact_name') or data.get('firstName')
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        firm_type = data.get('firm_type') or data.get('firmType')
        
        if not website_url:
            return jsonify({
                'success': False,
                'error': 'No website URL provided'
            }), 400
        
        # Start background processing
        thread = threading.Thread(
            target=process_audit_async,
            args=(contact_id, contact_email, contact_name, website_url, firm_type)
        )
        thread.start()
        
        # Immediately return success
        return jsonify({
            'success': True,
            'contact_id': contact_id,
            'message': 'Audit started - results will be sent to webhook when complete',
            'website_url': website_url
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
        'claude_key': bool(CLAUDE_API_KEY),
        'r2_configured': bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY),
        'ghl_webhook': bool(GHL_WEBHOOK_URL)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
