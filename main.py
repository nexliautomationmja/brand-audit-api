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
    
    base_prompt = """You are a brutally honest website and brand auditor for financial professionals. Analyze this website screenshot and score it out of 100 based on these four categories:

1. CREDIBILITY & TRUST (25 pts) - Does it look like a legitimate firm? Professional photos, credentials displayed, testimonials, trust badges, compliance disclosures
2. CLIENT EXPERIENCE (25 pts) - Mobile responsiveness, page speed indicators, navigation clarity, readability, modern design
3. DIFFERENTIATION (25 pts) - Clear value proposition, unique positioning, target client defined, what makes them different from 10,000 other advisors
4. CONVERSION PATH (25 pts) - Clear CTAs, easy contact options, booking capability, lead capture forms, next steps obvious

SCORING GUIDELINES - BE HARSH:
- 80-100: Exceptional (rare - only for truly outstanding sites)
- 70-79: Good (above average, minor improvements needed)
- 60-69: Average (meets basic standards but nothing special)
- 50-59: Below Average (significant issues hurting conversions)
- 40-49: Poor (major problems, likely losing clients)
- Below 40: Critical (site is actively hurting the business)

Most financial advisor websites should score between 45-65. A score above 70 should be RARE."""

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

Return ONLY valid JSON in this exact format:
{
    "overall_score": 52,
    "grade": "D",
    "categories": {
        "credibility_trust": {
            "score": 14,
            "findings": "What you observed about their credibility and trust signals",
            "opportunity": "Specific improvement they could make"
        },
        "client_experience": {
            "score": 12,
            "findings": "What you observed about UX, mobile, speed",
            "opportunity": "Specific improvement they could make"
        },
        "differentiation": {
            "score": 11,
            "findings": "What you observed about their unique positioning",
            "opportunity": "Specific improvement they could make"
        },
        "conversion_path": {
            "score": 15,
            "findings": "What you observed about CTAs and lead capture",
            "opportunity": "Specific improvement they could make"
        }
    },
    "recommendations": [
        {
            "priority": "HIGH",
            "issue": "The main problem",
            "impact": "How this affects their business",
            "recommendation": "What they should do"
        },
        {
            "priority": "HIGH",
            "issue": "Second problem",
            "impact": "Business impact",
            "recommendation": "What they should do"
        },
        {
            "priority": "MEDIUM",
            "issue": "Third problem",
            "impact": "Business impact",
            "recommendation": "What they should do"
        }
    ],
    "competitive_insight": "One paragraph comparing this site to what top-performing firms in their space do. Frame as 'firms that consistently attract high-value clients tend to...' - educational, not condescending.",
    "summary": "One sentence summary of the site's biggest weakness",
    "bottom_line": "2-3 sentences summarizing the site's current effectiveness at converting high-value prospects, framed as opportunity rather than criticism. End with a forward-looking statement."
}"""
    
    return base_prompt


PDF_PROMPT = """Create a professional, executive-style HTML document for a website assessment report tailored for financial advisors. Use this data:

{audit_data}

Website URL: {website_url}
Firm/Advisor Name: {business_name}
Assessment Date: {assessment_date}

CRITICAL - Use this exact SVG for the Nexli logo (the Breakthrough mark with wordmark):
<svg viewBox="0 0 140 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="logoGrad" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color:#2563EB"/>
            <stop offset="100%" style="stop-color:#06B6D4"/>
        </linearGradient>
    </defs>
    <path d="M4 36L20 24L4 12L4 20L12 24L4 28L4 36Z" fill="#2563EB"/>
    <path d="M12 36L28 24L12 12L12 18L18 24L12 30L12 36Z" fill="url(#logoGrad)"/>
    <path d="M20 36L44 24L20 12L20 18L32 24L20 30L20 36Z" fill="#06B6D4"/>
    <text x="52" y="32" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="800" letter-spacing="-1" fill="#0A1628">Nexli</text>
</svg>

Design requirements:
- Use Nexli branding: Primary blue #2563EB, Cyan accent #06B6D4, Dark #0A1628, Light gray #F8FAFC
- Clean, sophisticated design appropriate for financial professionals
- Professional typography (system fonts - use font-weight strategically)
- Executive summary style - scannable with clear hierarchy

Structure:
1. HEADER
   - Wrap the Nexli SVG logo in: <a href="https://www.nexli.net/#book" target="_blank" style="text-decoration:none;">...</a>
   - Make logo roughly 140px wide
   - "Digital Presence Assessment" as subtitle below logo
   - "Prepared for [business_name]"
   - Use the exact Assessment Date provided above (do NOT generate your own date)

2. EXECUTIVE SUMMARY
   - Overall score displayed prominently in a circle/badge (color-coded: green 80+, blue 60-79, orange 40-59, red below 40)
   - Grade letter next to it
   - The "summary" field as a one-liner
   - The "bottom_line" as a 2-3 sentence overview

3. ASSESSMENT BREAKDOWN
   - Four category cards in a 2x2 grid (or stacked on mobile)
   - Each card shows: Category name, Score as progress bar (out of 25), Findings, Opportunity
   - Use subtle background colors to differentiate

4. STRATEGIC RECOMMENDATIONS
   - List the 3 recommendations with priority badges (HIGH = red/orange, MEDIUM = blue)
   - Each shows: Issue, Impact, Recommendation
   - Frame as "opportunities" not "problems"

5. COMPETITIVE INSIGHT
   - Styled as a quote/callout box
   - The "competitive_insight" paragraph

6. NEXT STEPS CTA - THIS SECTION IS REQUIRED
   - Professional call-to-action section with a light blue (#EFF6FF) background
   - Include the clickable Nexli logo SVG wrapped in <a href="https://www.nexli.net/#book" target="_blank">
   - Headline: "Ready to Elevate Your Digital Presence?"
   - Subtext: "Schedule a complimentary strategy session to discuss how these insights apply to your firm's growth goals."
   - MUST include this EXACT button code (copy exactly as shown):
     <a href="https://www.nexli.net/#book" target="_blank" style="display:inline-block; background: linear-gradient(135deg, #2563EB 0%, #06B6D4 100%); color:white; padding:16px 32px; border-radius:8px; text-decoration:none; font-weight:600; font-size:18px; margin:20px 0;">Book Your Strategy Call</a>
   - Below button: "No obligation • 30-minute consultation • Tailored recommendations" (small, gray text, centered)

7. FOOTER
   - Small clickable Nexli logo wrapped in <a href="https://www.nexli.net/#book" target="_blank">
   - "Assessment powered by Nexli"
   - "Helping financial advisors attract and convert high-value clients"
   - Small disclaimer: "This assessment is based on automated analysis and publicly visible website elements."

Make it print-friendly with proper margins. The tone should feel like a report from a peer consultant, not a criticism from a vendor. Return ONLY the HTML, no markdown code fences."""


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
