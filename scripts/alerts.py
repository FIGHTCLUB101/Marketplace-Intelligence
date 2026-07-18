"""Email alerts for the weekly competitive report. build_shelf_section_html
and build_oats_section_html each render one platform's changes as an HTML
fragment (no outer <html>/<head> wrapper); build_combined_email_html wraps
one or more fragments into a single document with one severity banner
covering all included platforms. build_email_html is a back-compat wrapper
for the single-platform (blinkit_goatlife-only) case.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shelf_changes import generate_narrative_summary, goat_gone_unique

_STYLE = """
  body { font-family: Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }
  .container { max-width: 620px; margin: 0 auto; background: white; }
  .header { background: #0d0d0d; color: white; padding: 28px 32px; }
  .severity { padding: 16px 32px; font-size: 17px; font-weight: bold; }
  .platform-title { padding: 16px 32px 0; margin: 0; font-size: 16px; border-top: 4px solid #0d0d0d; }
  .section { padding: 20px 32px; border-bottom: 1px solid #eee; }
  .alert-item { background: #fff5f5; border-left: 3px solid #e53e3e; padding: 10px 14px; margin-bottom: 8px; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { background: #f0f0f0; padding: 8px; text-align: left; }
  td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
"""


def build_shelf_section_html(changes, label):
    """HTML fragment for one rank-based (blinkit_goatlife-style) platform."""
    unique_gone = goat_gone_unique(changes)
    narrative_html = "<br>".join(generate_narrative_summary(changes))

    html = f'<h2 class="platform-title">{label}</h2>'
    html += f'<div class="section"><p>{narrative_html}</p></div>'

    if changes["goat_displaced"]:
        html += '<div class="section"><h3>GOAT Life Rank Disruptions</h3>'
        for item in changes["goat_displaced"]:
            html += (f'<div class="alert-item"><strong>{item["was"][:40]}</strong> displaced in '
                      f'{item["city"]} ({item["locality"]}) — {item["now"]}</div>')
        html += "</div>"

    if unique_gone:
        html += '<div class="section"><h3>GOAT Life Products No Longer Listed</h3>'
        for item in unique_gone:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> no longer listed in '
                      f'{item["city"]} ({item["locality"]}) — last seen rank {item["rank"]}</div>')
        html += "</div>"

    if changes["rank_intrusions"]:
        html += '<div class="section"><h3>Competitors in GOAT Territory</h3>'
        for item in changes["rank_intrusions"]:
            html += (f'<div class="alert-item"><strong>{item["intruder"][:40]}</strong> at rank '
                      f'{item["rank"]} in {item["city"]} ({item["locality"]})</div>')
        html += "</div>"

    if changes["price_changes"]:
        html += ('<div class="section"><h3>Price Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    return html


def build_oats_section_html(changes, label):
    """HTML fragment for one price/availability-based (oats platform) section."""
    html = f'<h2 class="platform-title">{label}</h2>'
    any_changes = False

    if changes["new_products"]:
        any_changes = True
        html += '<div class="section"><h3>New Products</h3>'
        for item in changes["new_products"]:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> appeared in '
                      f'{item["city"]} ({item["locality"]}) — {item["brand_searched"]}</div>')
        html += "</div>"

    if changes["gone_products"]:
        any_changes = True
        html += '<div class="section"><h3>Delisted Products</h3>'
        for item in changes["gone_products"]:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> no longer listed in '
                      f'{item["city"]} ({item["locality"]}) — {item["brand_searched"]}</div>')
        html += "</div>"

    if changes["price_changes"]:
        any_changes = True
        html += ('<div class="section"><h3>Price Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    if changes["stock_changes"]:
        any_changes = True
        html += ('<div class="section"><h3>Stock Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["stock_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>{item["old_stock"]}</td>'
                      f'<td>{item["new_stock"]}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    if not any_changes:
        html += '<div class="section"><p>No changes detected this week.</p></div>'

    return html


def build_combined_email_html(sections, new_run_label, old_run_label):
    """sections: list of {"label": str, "mode": "rank" | "oats", "changes": dict}.
    Renders one document: header, a total-change-count severity banner, then
    one section fragment per platform."""
    total = 0
    fragments = []
    for s in sections:
        changes = s["changes"]
        total += sum(len(v) for v in changes.values())
        if s["mode"] == "rank":
            fragments.append(build_shelf_section_html(changes, s["label"]))
        else:
            fragments.append(build_oats_section_html(changes, s["label"]))

    severity = "ALL CLEAR" if total == 0 else f"{total} CHANGES DETECTED"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
{_STYLE}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>Weekly Competitive Report</h1>
    <div>{old_run_label} to {new_run_label}</div></div>
  <div class="severity">{severity}</div>
"""
    html += "".join(fragments)
    html += "</div></body></html>"
    return html


def build_email_html(changes, new_run_label, old_run_label):
    """Back-compat single-platform wrapper (blinkit_goatlife-only callers)."""
    return build_combined_email_html(
        [{"label": "GOAT Life Shelf Monitor", "mode": "rank", "changes": changes}],
        new_run_label, old_run_label,
    )


def send_gmail(subject, html_body, sender, app_password, recipients):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipients, msg.as_string())
