"""Email alerts, ported near-verbatim from the antigravity repo's
shelf_monitor.py (build_email_html/send_gmail). Takes the new-style
detect_changes() dict shape (new_products/gone_products, not
new_competitors/gone_competitors) from shelf_changes.py.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shelf_changes import generate_narrative_summary, goat_gone_unique


def build_email_html(changes, new_run_label, old_run_label):
    unique_gone = goat_gone_unique(changes)
    total_displaced = len(changes["goat_displaced"]) + len(unique_gone)
    total_intrusions = len(changes["rank_intrusions"])

    severity = "ALL CLEAR" if total_displaced == 0 and total_intrusions == 0 else \
               "CHANGES DETECTED" if total_displaced == 0 else \
               "GOAT LIFE SHELF DISRUPTED"

    narrative_html = "<br>".join(generate_narrative_summary(changes))

    html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }}
  .container {{ max-width: 620px; margin: 0 auto; background: white; }}
  .header {{ background: #0d0d0d; color: white; padding: 28px 32px; }}
  .severity {{ padding: 16px 32px; font-size: 17px; font-weight: bold; }}
  .section {{ padding: 20px 32px; border-bottom: 1px solid #eee; }}
  .alert-item {{ background: #fff5f5; border-left: 3px solid #e53e3e; padding: 10px 14px; margin-bottom: 8px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #f0f0f0; padding: 8px; text-align: left; }}
  td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; }}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>GOAT Life — Shelf Monitor</h1>
    <div>{old_run_label} to {new_run_label}</div></div>
  <div class="severity">{severity}</div>
  <div class="section"><p>{narrative_html}</p></div>
"""

    if changes["goat_displaced"]:
        html += '<div class="section"><h2>GOAT Life Rank Disruptions</h2>'
        for item in changes["goat_displaced"]:
            html += (f'<div class="alert-item"><strong>{item["was"][:40]}</strong> displaced in '
                      f'{item["city"]} ({item["locality"]}) — {item["now"]}</div>')
        html += "</div>"

    if unique_gone:
        html += '<div class="section"><h2>GOAT Life Products No Longer Listed</h2>'
        for item in unique_gone:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> no longer listed in '
                      f'{item["city"]} ({item["locality"]}) — last seen rank {item["rank"]}</div>')
        html += "</div>"

    if changes["rank_intrusions"]:
        html += '<div class="section"><h2>Competitors in GOAT Territory</h2>'
        for item in changes["rank_intrusions"]:
            html += (f'<div class="alert-item"><strong>{item["intruder"][:40]}</strong> at rank '
                      f'{item["rank"]} in {item["city"]} ({item["locality"]})</div>')
        html += "</div>"

    if changes["price_changes"]:
        html += "<div class=\"section\"><h2>Price Changes</h2><table><tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>"
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    html += "</div></body></html>"
    return html


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
