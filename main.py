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
- 90-100: A (Exceptional - rare, truly outstanding)
- 80-89: B (Good - above average, minor improvements needed)
- 70-79: C (Average - meets basic standards but nothing special)
- 60-69: D (Below Average - significant issues hurting conversions)
- Below 60: F (Failing - major problems, site is hurting the business)

IMPORTANT: The letter grade MUST match the score:
- Score 52 = Grade F
- Score 67 = Grade D
- Score 73 = Grade C
- Score 85 = Grade B
- Score 92 = Grade A

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
    "grade": "F",
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


def get_score_color(score):
    """Return the appropriate gradient colors based on score"""
    if score >= 80:
        return "#10B981", "#059669"  # Green
    elif score >= 60:
        return "#3B82F6", "#2563EB"  # Blue
    elif score >= 40:
        return "#F97316", "#EA580C"  # Orange
    else:
        return "#EF4444", "#DC2626"  # Red


def generate_html_template(audit_data, website_url, business_name, assessment_date):
    """Generate HTML report using hardcoded template with exact approved design"""
    
    score = audit_data.get('overall_score', 0)
    grade = audit_data.get('grade', 'N/A')
    summary = audit_data.get('summary', '')
    bottom_line = audit_data.get('bottom_line', '')
    competitive_insight = audit_data.get('competitive_insight', '')
    
    categories = audit_data.get('categories', {})
    cred = categories.get('credibility_trust', {})
    exp = categories.get('client_experience', {})
    diff = categories.get('differentiation', {})
    conv = categories.get('conversion_path', {})
    
    recommendations = audit_data.get('recommendations', [])
    
    score_color1, score_color2 = get_score_color(score)
    
    # Build recommendations HTML
    recs_html = ""
    for rec in recommendations[:3]:
        priority = rec.get('priority', 'MEDIUM').upper()
        priority_class = "high" if priority == "HIGH" else "medium"
        badge_bg = "#FEE2E2" if priority == "HIGH" else "#FEF3C7"
        badge_color = "#DC2626" if priority == "HIGH" else "#D97706"
        border_color = "#EF4444" if priority == "HIGH" else "#F59E0B"
        
        recs_html += f'''
            <div class="recommendation" style="border-left-color: {border_color};">
                <span class="priority-badge" style="background: {badge_bg}; color: {badge_color};">{priority} Priority</span>
                <h3>{rec.get('issue', '')}</h3>
                <p><strong>Impact:</strong> {rec.get('impact', '')}</p>
                <p class="action">→ {rec.get('recommendation', '')}</p>
            </div>
        '''
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Digital Presence Assessment - {business_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #F8FAFC;
            color: #0A1628;
            line-height: 1.6;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        
        /* Header */
        .header {{
            background: linear-gradient(135deg, #0A1628 0%, #1a2942 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header a {{
            text-decoration: none;
        }}
        .logo {{
            margin-bottom: 20px;
            display: inline-block;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 300;
            margin-bottom: 8px;
            color: white;
        }}
        .header .subtitle {{
            font-size: 18px;
            opacity: 0.9;
        }}
        .header .meta {{
            margin-top: 16px;
            font-size: 14px;
            opacity: 0.7;
        }}
        
        /* Executive Summary */
        .executive-summary {{
            padding: 40px;
            display: flex;
            gap: 40px;
            align-items: center;
            border-bottom: 1px solid #E2E8F0;
        }}
        .score-circle {{
            width: 140px;
            height: 140px;
            border-radius: 50%;
            background: linear-gradient(135deg, {score_color1} 0%, {score_color2} 100%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: white;
            flex-shrink: 0;
        }}
        .score-circle .score {{
            font-size: 48px;
            font-weight: 700;
            line-height: 1;
        }}
        .score-circle .grade {{
            font-size: 24px;
            font-weight: 600;
            opacity: 0.9;
        }}
        .summary-text h2 {{
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #64748B;
            margin-bottom: 12px;
        }}
        .summary-text .summary {{
            font-size: 18px;
            font-weight: 600;
            color: #0A1628;
            margin-bottom: 16px;
        }}
        .summary-text .bottom-line {{
            font-size: 15px;
            color: #475569;
        }}
        
        /* Assessment Breakdown */
        .breakdown {{
            padding: 40px;
            background: #F8FAFC;
        }}
        .breakdown h2 {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 24px;
            color: #0A1628;
        }}
        .category-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .category-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }}
        .category-card h3 {{
            font-size: 16px;
            font-weight: 600;
            color: #0A1628;
            margin-bottom: 12px;
        }}
        .score-bar {{
            height: 8px;
            background: #E2E8F0;
            border-radius: 4px;
            margin-bottom: 8px;
            overflow: hidden;
        }}
        .score-bar-fill {{
            height: 100%;
            border-radius: 4px;
            background: linear-gradient(90deg, #2563EB, #06B6D4);
        }}
        .score-label {{
            font-size: 14px;
            font-weight: 600;
            color: #2563EB;
            margin-bottom: 12px;
        }}
        .category-card h4 {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748B;
            margin-bottom: 4px;
        }}
        .category-card p {{
            font-size: 14px;
            color: #475569;
            margin-bottom: 12px;
        }}
        
        /* Recommendations */
        .recommendations {{
            padding: 40px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .recommendations h2 {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 24px;
            color: #0A1628;
        }}
        .recommendation {{
            background: #F8FAFC;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            border-left: 4px solid #2563EB;
        }}
        .priority-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }}
        .recommendation h3 {{
            font-size: 16px;
            font-weight: 600;
            color: #0A1628;
            margin-bottom: 8px;
        }}
        .recommendation p {{
            font-size: 14px;
            color: #475569;
            margin-bottom: 8px;
        }}
        .recommendation .action {{
            font-size: 14px;
            color: #2563EB;
            font-weight: 500;
        }}
        
        /* Competitive Insight */
        .competitive-insight {{
            padding: 40px;
            background: #EFF6FF;
            border-left: 4px solid #2563EB;
            margin: 0 40px 40px 40px;
            border-radius: 0 12px 12px 0;
        }}
        .competitive-insight h2 {{
            font-size: 16px;
            font-weight: 700;
            color: #1E40AF;
            margin-bottom: 12px;
        }}
        .competitive-insight p {{
            font-size: 15px;
            color: #1E3A8A;
            font-style: italic;
        }}
        
        /* CTA Section */
        .cta-section {{
            background: #EFF6FF;
            padding: 60px 40px;
            text-align: center;
        }}
        .cta-section .logo {{
            margin-bottom: 24px;
        }}
        .cta-section h2 {{
            font-size: 28px;
            font-weight: 700;
            color: #0A1628;
            margin-bottom: 12px;
        }}
        .cta-section .subtext {{
            font-size: 16px;
            color: #475569;
            margin-bottom: 24px;
            max-width: 500px;
            margin-left: auto;
            margin-right: auto;
        }}
        .cta-button {{
            display: inline-block;
            background: linear-gradient(135deg, #2563EB 0%, #06B6D4 100%);
            color: white;
            padding: 16px 32px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 18px;
            margin: 20px 0;
        }}
        .cta-meta {{
            font-size: 14px;
            color: #64748B;
            margin-top: 16px;
        }}
        
        /* Footer */
        .footer {{
            background: #0A1628;
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .footer a {{
            text-decoration: none;
        }}
        .footer .logo {{
            margin-bottom: 16px;
        }}
        .footer p {{
            font-size: 14px;
            opacity: 0.8;
            margin-bottom: 8px;
        }}
        .footer .disclaimer {{
            font-size: 12px;
            opacity: 0.5;
            margin-top: 20px;
        }}
        
        @media (max-width: 600px) {{
            .category-grid {{
                grid-template-columns: 1fr;
            }}
            .executive-summary {{
                flex-direction: column;
                text-align: center;
            }}
        }}
        
        @media print {{
            .container {{
                box-shadow: none;
            }}
            .cta-button {{
                background: #2563EB !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <a href="https://www.nexli.net/#book" target="_blank" class="logo">
                <svg viewBox="0 0 140 48" width="140" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <linearGradient id="logoGrad" x1="0%" y1="100%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:#2563EB"/>
                            <stop offset="100%" style="stop-color:#06B6D4"/>
                        </linearGradient>
                    </defs>
                    <path d="M4 36L20 24L4 12L4 20L12 24L4 28L4 36Z" fill="#2563EB"/>
                    <path d="M12 36L28 24L12 12L12 18L18 24L12 30L12 36Z" fill="url(#logoGrad)"/>
                    <path d="M20 36L44 24L20 12L20 18L32 24L20 30L20 36Z" fill="#06B6D4"/>
                    <text x="52" y="32" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="800" letter-spacing="-1" fill="white">Nexli</text>
                </svg>
            </a>
            <h1>Digital Presence Assessment</h1>
            <p class="subtitle">Prepared for <strong>{business_name}</strong></p>
            <p class="meta"><strong>Website:</strong> {website_url} &nbsp;|&nbsp; <strong>Assessment Date:</strong> {assessment_date}</p>
        </header>
        
        <!-- Executive Summary -->
        <section class="executive-summary">
            <div class="score-circle">
                <span class="score">{score}</span>
                <span class="grade">{grade}</span>
            </div>
            <div class="summary-text">
                <h2>Executive Summary</h2>
                <p class="summary">{summary}</p>
                <p class="bottom-line">{bottom_line}</p>
            </div>
        </section>
        
        <!-- First Impression Notice -->
        <div style="background: #FEF3C7; border-left: 4px solid #F59E0B; padding: 16px 24px; margin: 0 40px 0 40px;">
            <p style="margin: 0; font-size: 14px; color: #92400E;"><strong>Why "Above the Fold" Matters:</strong> This assessment evaluates what visitors see in the first 3 seconds—before scrolling. Research shows most users decide to stay or leave within this window. If key trust signals, value propositions, or calls-to-action are buried below the fold, visitors may never see them. The best-performing websites put their most important content front and center.</p>
        </div>
        
        <!-- Assessment Breakdown -->
        <section class="breakdown">
            <h2>Assessment Breakdown</h2>
            <div class="category-grid">
                <div class="category-card">
                    <h3>Credibility & Trust</h3>
                    <div class="score-bar"><div class="score-bar-fill" style="width: {cred.get('score', 0) * 4}%;"></div></div>
                    <p class="score-label">{cred.get('score', 0)}/25</p>
                    <h4>Current State</h4>
                    <p>{cred.get('findings', '')}</p>
                    <h4>Opportunity</h4>
                    <p>{cred.get('opportunity', '')}</p>
                </div>
                <div class="category-card">
                    <h3>Client Experience</h3>
                    <div class="score-bar"><div class="score-bar-fill" style="width: {exp.get('score', 0) * 4}%;"></div></div>
                    <p class="score-label">{exp.get('score', 0)}/25</p>
                    <h4>Current State</h4>
                    <p>{exp.get('findings', '')}</p>
                    <h4>Opportunity</h4>
                    <p>{exp.get('opportunity', '')}</p>
                </div>
                <div class="category-card">
                    <h3>Differentiation</h3>
                    <div class="score-bar"><div class="score-bar-fill" style="width: {diff.get('score', 0) * 4}%;"></div></div>
                    <p class="score-label">{diff.get('score', 0)}/25</p>
                    <h4>Current State</h4>
                    <p>{diff.get('findings', '')}</p>
                    <h4>Opportunity</h4>
                    <p>{diff.get('opportunity', '')}</p>
                </div>
                <div class="category-card">
                    <h3>Conversion Path</h3>
                    <div class="score-bar"><div class="score-bar-fill" style="width: {conv.get('score', 0) * 4}%;"></div></div>
                    <p class="score-label">{conv.get('score', 0)}/25</p>
                    <h4>Current State</h4>
                    <p>{conv.get('findings', '')}</p>
                    <h4>Opportunity</h4>
                    <p>{conv.get('opportunity', '')}</p>
                </div>
            </div>
        </section>
        
        <!-- Strategic Recommendations -->
        <section class="recommendations">
            <h2>Strategic Recommendations</h2>
            {recs_html}
        </section>
        
        <!-- Competitive Insight -->
        <div class="competitive-insight">
            <h2>Competitive Insight</h2>
            <p>{competitive_insight}</p>
        </div>
        
        <!-- CTA Section -->
        <section class="cta-section">
            <a href="https://www.nexli.net/#book" target="_blank" class="logo">
                <svg viewBox="0 0 140 48" width="140" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <linearGradient id="logoGrad2" x1="0%" y1="100%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:#2563EB"/>
                            <stop offset="100%" style="stop-color:#06B6D4"/>
                        </linearGradient>
                    </defs>
                    <path d="M4 36L20 24L4 12L4 20L12 24L4 28L4 36Z" fill="#2563EB"/>
                    <path d="M12 36L28 24L12 12L12 18L18 24L12 30L12 36Z" fill="url(#logoGrad2)"/>
                    <path d="M20 36L44 24L20 12L20 18L32 24L20 30L20 36Z" fill="#06B6D4"/>
                    <text x="52" y="32" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="800" letter-spacing="-1" fill="#0A1628">Nexli</text>
                </svg>
            </a>
            <h2>Ready to Elevate Your Digital Presence?</h2>
            <p class="subtext">Schedule a complimentary strategy session to discuss how these insights apply to your firm's growth goals.</p>
            <a href="https://www.nexli.net/#book" target="_blank" class="cta-button">Book Your Strategy Call</a>
            <p class="cta-meta">No obligation • 30-minute consultation • Tailored recommendations</p>
        </section>
        
        <!-- Footer -->
        <footer class="footer">
            <a href="https://www.nexli.net/#book" target="_blank" class="logo">
                <svg viewBox="0 0 48 48" width="48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M4 36L20 24L4 12L4 20L12 24L4 28L4 36Z" fill="rgba(255,255,255,0.5)"/>
                    <path d="M12 36L28 24L12 12L12 18L18 24L12 30L12 36Z" fill="rgba(255,255,255,0.75)"/>
                    <path d="M20 36L44 24L20 12L20 18L32 24L20 30L20 36Z" fill="white"/>
                </svg>
            </a>
            <p>Assessment powered by Nexli</p>
            <p>Helping financial advisors attract and convert high-value clients</p>
            <p class="disclaimer">This assessment is based on automated analysis and publicly visible website elements.</p>
        </footer>
    </div>
</body>
</html>'''
    
    return html


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
        
        # Step 2: Claude analysis
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
        
        # Step 3: Generate HTML report using hardcoded template (NOT Claude)
        print("Generating HTML report...")
        assessment_date = datetime.now().strftime("%B %d, %Y")
        html_report = generate_html_template(
            audit_data=audit_data,
            website_url=website_url,
            business_name=contact_name or "Your Firm",
            assessment_date=assessment_date
        )
        
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
        
        # Log incoming data for debugging
        print(f"Received data: {json.dumps(data, indent=2)}")
        
        # Extract fields (handle various field names)
        contact_id = data.get('id') or data.get('contact_id') or data.get('contactId')
        contact_email = data.get('email') or data.get('contact_email')
        contact_name = data.get('name') or data.get('contact_name') or data.get('firstName')
        website_url = data.get('website_url') or data.get('websiteUrl') or data.get('website') or data.get('url')
        firm_type = data.get('firm_type') or data.get('firmType')
        
        print(f"Parsed - Name: {contact_name}, Email: {contact_email}, URL: {website_url}, Firm Type: {firm_type}")
        
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
