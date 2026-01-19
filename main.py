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

GRADING_PROMPTS = {
    "wealth_management": """You are a digital marketing strategist specializing in wealth management firms. Analyze this website from the perspective of a high-net-worth prospect ($500K+ investable assets) evaluating whether to trust this advisor with their wealth.

YOUR JOB IS TO BE HONEST - NOT HARSH, NOT GENEROUS. JUST ACCURATE.

Score each category out of 25 points based on what you actually observe. The overall score is the sum of all four categories.

SCORING GUIDE:
- 20-25: Excellent - This aspect is genuinely well-executed
- 15-19: Good - Solid but has room for improvement
- 10-14: Fair - Noticeable issues that hurt effectiveness
- 5-9: Poor - Significant problems
- 0-4: Failing - Fundamentally broken or missing

GRADE SCALE (based on overall score out of 100):
- 90-100: A
- 80-89: B
- 70-79: C
- 60-69: D
- Below 60: F
(Add + or - as appropriate, e.g., 85 = B, 78 = C+, 62 = D-)

CATEGORIES TO EVALUATE FOR WEALTH MANAGEMENT:

1. CREDIBILITY & TRUST (25 pts)
   - Professional credentials displayed (CFP, CFA, CIMA, ChFC)?
   - Fiduciary status clearly stated?
   - SEC/FINRA disclosures accessible?
   - Firm history, team bios, AUM indicators?
   - Does it look like a legitimate wealth management firm?

2. CLIENT EXPERIENCE (25 pts)
   - Clear value proposition for high-net-worth clients?
   - Investment philosophy communicated?
   - Easy navigation, mobile-friendly, modern design?
   - Professional imagery (not cheap stock photos)?

3. DIFFERENTIATION (25 pts)
   - What makes this firm different from other RIAs?
   - Target client clearly defined (executives, business owners, retirees)?
   - Specialized services (tax planning, estate, equity compensation)?
   - Unique investment approach or philosophy?

4. CONVERSION PATH (25 pts)
   - Clear call-to-action for qualified prospects?
   - Easy way to schedule a consultation?
   - Lead capture for prospects not ready to talk?
   - Fee transparency or "what to expect" information?

Return ONLY valid JSON in this exact format (replace all values with your actual assessment):
{
    "overall_score": [SUM OF FOUR CATEGORY SCORES],
    "grade": "[LETTER GRADE BASED ON SCORE]",
    "summary": "[One sentence about the site's current state]",
    "categories": {
        "credibility_trust": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What improving this could mean for their practice]"
        },
        "client_experience": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Impact on prospect engagement]"
        },
        "differentiation": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What clear positioning could do for them]"
        },
        "conversion_path": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Potential improvement in conversions]"
        }
    },
    "strategic_recommendations": [
        {
            "priority": "HIGH",
            "issue": "[Most important issue you identified]",
            "impact": "[How this affects their ability to attract HNW clients]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Second issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Third issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        }
    ],
    "competitive_insight": "[One paragraph comparing this site to what top-performing wealth management firms typically do.]",
    "bottom_line": "[2-3 sentences summarizing effectiveness and opportunity. Be honest but constructive.]"
}""",

    "cpa": """You are a digital marketing strategist specializing in CPA and accounting firms. Analyze this website from the perspective of a business owner or high-income individual looking for a trusted CPA.

YOUR JOB IS TO BE HONEST - NOT HARSH, NOT GENEROUS. JUST ACCURATE.

Score each category out of 25 points based on what you actually observe. The overall score is the sum of all four categories.

SCORING GUIDE:
- 20-25: Excellent - This aspect is genuinely well-executed
- 15-19: Good - Solid but has room for improvement
- 10-14: Fair - Noticeable issues that hurt effectiveness
- 5-9: Poor - Significant problems
- 0-4: Failing - Fundamentally broken or missing

GRADE SCALE (based on overall score out of 100):
- 90-100: A
- 80-89: B
- 70-79: C
- 60-69: D
- Below 60: F
(Add + or - as appropriate, e.g., 85 = B, 78 = C+, 62 = D-)

CATEGORIES TO EVALUATE FOR CPA/ACCOUNTING FIRMS:

1. CREDIBILITY & TRUST (25 pts)
   - CPA credentials clearly displayed?
   - State licensure mentioned?
   - Professional memberships (AICPA, state society)?
   - Firm history, team qualifications?
   - Security and confidentiality signals?

2. CLIENT EXPERIENCE (25 pts)
   - Services clearly listed (tax prep, bookkeeping, advisory, audit)?
   - Industry specializations shown (real estate, medical, small business)?
   - Easy navigation, modern design?
   - Client portal access visible?

3. DIFFERENTIATION (25 pts)
   - What makes this CPA different from others?
   - Niche industries or client types served?
   - Proactive tax planning vs just compliance?
   - Technology-forward approach?

4. CONVERSION PATH (25 pts)
   - Clear call-to-action for new clients?
   - Easy way to request a consultation or quote?
   - Contact information prominently displayed?
   - Lead capture for tax season or newsletter?

Return ONLY valid JSON in this exact format (replace all values with your actual assessment):
{
    "overall_score": [SUM OF FOUR CATEGORY SCORES],
    "grade": "[LETTER GRADE BASED ON SCORE]",
    "summary": "[One sentence about the site's current state]",
    "categories": {
        "credibility_trust": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What improving this could mean for their practice]"
        },
        "client_experience": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Impact on prospect engagement]"
        },
        "differentiation": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What clear positioning could do for them]"
        },
        "conversion_path": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Potential improvement in conversions]"
        }
    },
    "strategic_recommendations": [
        {
            "priority": "HIGH",
            "issue": "[Most important issue you identified]",
            "impact": "[How this affects their ability to attract clients]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Second issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Third issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        }
    ],
    "competitive_insight": "[One paragraph comparing this site to what top-performing CPA firms typically do.]",
    "bottom_line": "[2-3 sentences summarizing effectiveness and opportunity. Be honest but constructive.]"
}""",

    "financial_advisor": """You are a digital marketing strategist specializing in financial advisory firms. Analyze this website from the perspective of someone looking for a financial advisor to help with their financial planning needs.

YOUR JOB IS TO BE HONEST - NOT HARSH, NOT GENEROUS. JUST ACCURATE.

Score each category out of 25 points based on what you actually observe. The overall score is the sum of all four categories.

SCORING GUIDE:
- 20-25: Excellent - This aspect is genuinely well-executed
- 15-19: Good - Solid but has room for improvement
- 10-14: Fair - Noticeable issues that hurt effectiveness
- 5-9: Poor - Significant problems
- 0-4: Failing - Fundamentally broken or missing

GRADE SCALE (based on overall score out of 100):
- 90-100: A
- 80-89: B
- 70-79: C
- 60-69: D
- Below 60: F
(Add + or - as appropriate, e.g., 85 = B, 78 = C+, 62 = D-)

CATEGORIES TO EVALUATE FOR FINANCIAL ADVISORS:

1. CREDIBILITY & TRUST (25 pts)
   - Professional credentials displayed (CFP, ChFC, CLU)?
   - Fiduciary status or fee structure clarity?
   - Regulatory disclosures accessible?
   - Team bios and firm background?
   - Professional appearance?

2. CLIENT EXPERIENCE (25 pts)
   - Clear explanation of services (retirement, insurance, estate)?
   - Who they help best (young professionals, families, pre-retirees)?
   - Easy navigation, mobile-friendly design?
   - Educational content or resources?

3. DIFFERENTIATION (25 pts)
   - What makes this advisor different?
   - Planning philosophy or approach clear?
   - Target client defined?
   - Specialized expertise shown?

4. CONVERSION PATH (25 pts)
   - Clear call-to-action?
   - Easy way to schedule a meeting?
   - Free consultation or financial checkup offered?
   - Lead magnet or newsletter signup?

Return ONLY valid JSON in this exact format (replace all values with your actual assessment):
{
    "overall_score": [SUM OF FOUR CATEGORY SCORES],
    "grade": "[LETTER GRADE BASED ON SCORE]",
    "summary": "[One sentence about the site's current state]",
    "categories": {
        "credibility_trust": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What improving this could mean for their practice]"
        },
        "client_experience": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Impact on prospect engagement]"
        },
        "differentiation": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[What clear positioning could do for them]"
        },
        "conversion_path": {
            "score": [0-25],
            "findings": "[What you actually observe - be specific]",
            "opportunity": "[Potential improvement in conversions]"
        }
    },
    "strategic_recommendations": [
        {
            "priority": "HIGH",
            "issue": "[Most important issue you identified]",
            "impact": "[How this affects their ability to attract clients]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Second issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        },
        {
            "priority": "MEDIUM",
            "issue": "[Third issue]",
            "impact": "[Business impact]",
            "recommendation": "[Actionable suggestion]"
        }
    ],
    "competitive_insight": "[One paragraph comparing this site to what top-performing financial advisors typically do.]",
    "bottom_line": "[2-3 sentences summarizing effectiveness and opportunity. Be honest but constructive.]"
}"""
}

# Default prompt if no firm type specified
DEFAULT_GRADING_PROMPT = GRADING_PROMPTS["financial_advisor"]

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

CRITICAL REQUIREMENTS:
1. ALL Nexli logos must be wrapped in an <a href="https://www.nexli.net/#book" target="_blank"> tag so they are clickable
2. The CTA section MUST have a visible, styled button with the text "Book Your Strategy Call"

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
   - Below button: "No obligation • 30-minute consultation • Tailored recommendations"

7. LARGE CTA BUTTON AT THE VERY BOTTOM - REQUIRED
   - At the absolute bottom of the document, before the footer, add this exact button centered:
   <div style="text-align:center; padding:40px 20px; background:#EFF6FF;">
     <a href="https://www.nexli.net/#book" target="_blank" style="display:inline-block; background:linear-gradient(135deg, #2563EB 0%, #06B6D4 100%); color:white; padding:18px 48px; border-radius:50px; text-decoration:none; font-weight:700; font-size:18px; box-shadow:0 4px 14px rgba(37,99,235,0.3);">Book Consultation</a>
   </div>

8. FOOTER
   - Small clickable Nexli logo wrapped in <a href="https://www.nexli.net/#book" target="_blank">
   - "Assessment powered by Nexli"
   - "Helping financial advisors attract and convert high-value clients"
   - Small disclaimer: "This assessment is based on automated analysis and publicly visible website elements."

Make it print-friendly with proper margins. The tone should feel like a report from a peer consultant, not a criticism from a vendor. Return ONLY the HTML, no markdown code fences."""


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


def analyze_with_gemini(screenshot_base64, firm_type=None):
    """Analyze screenshot with Gemini Vision"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    # Select the appropriate grading prompt based on firm type
    firm_type_key = None
    if firm_type:
        firm_type_lower = firm_type.lower().strip()
        if "wealth" in firm_type_lower:
            firm_type_key = "wealth_management"
        elif "cpa" in firm_type_lower or "account" in firm_type_lower:
            firm_type_key = "cpa"
        else:
            firm_type_key = "financial_advisor"
    
    grading_prompt = GRADING_PROMPTS.get(firm_type_key, DEFAULT_GRADING_PROMPT)
    
    payload = {
        "contents": [{
            "parts": [
                {"text": grading_prompt},
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
                business_name=business_name or "the business",
                assessment_date=datetime.now().strftime("%B %d, %Y")
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


def process_audit_async(contact_id, contact_email, contact_name, website_url, firm_type=None):
    """Background task to process the audit"""
    report_url = None
    audit_data = None
    
    try:
        print(f"Starting audit for {website_url} (firm type: {firm_type or 'default'})")
        
        # Step 1: Screenshot
        print("Taking screenshot...")
        screenshot = take_screenshot(website_url)
        
        # Step 2: Gemini analysis
        print("Analyzing with Gemini...")
        audit_json = analyze_with_gemini(screenshot, firm_type)
        
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
        firm_type = data.get('firm_type') or data.get('firmType') or data.get('type')
        
        if not website_url:
            return jsonify({'success': False, 'error': 'No website URL provided'}), 400
        
        # Normalize URL - add https:// if missing
        website_url = website_url.strip()
        if not website_url.startswith('http://') and not website_url.startswith('https://'):
            website_url = 'https://' + website_url
        
        # Start background processing
        thread = threading.Thread(
            target=process_audit_async,
            args=(contact_id, contact_email, contact_name, website_url, firm_type)
        )
        thread.daemon = True
        thread.start()
        
        # Immediately return success
        return jsonify({
            'success': True,
            'message': 'Audit started - results will be sent to webhook when complete',
            'website_url': website_url,
            'contact_id': contact_id,
            'firm_type': firm_type
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
