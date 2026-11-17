"""Generates small SYNTHETIC RSS files so the app runs offline. These are not real news."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

STORIES = {
    "technology": [
        ("Open-source language model tops reasoning benchmark", "A research group released an open-source language model that scored highly on a public reasoning benchmark. The model was trained with a mixture of synthetic and curated data. Researchers said evaluation on more diverse tasks is still needed. The weights are available under a permissive licence."),
        ("Chipmaker unveils energy-efficient AI accelerator", "A semiconductor company announced an accelerator designed for running machine learning inference at low power. The company claims improved performance per watt compared with its previous generation. Independent benchmarks have not yet been published. Shipments are planned for next year."),
        ("Universities expand machine learning curriculum", "Several engineering colleges are adding courses on machine learning operations and responsible AI. Faculty said students need practical experience deploying models. The new courses include projects on data pipelines and model monitoring. Industry partners will provide guest lectures."),
        ("Cybersecurity agencies warn about phishing using deepfake audio", "Security agencies issued guidance about phishing calls that use synthetic voices. Attackers imitate executives to request urgent payments. The guidance recommends verification through a second channel. Organisations are advised to train staff to recognise such requests."),
        ("New framework simplifies deploying Python web services", "Developers released a framework update that reduces boilerplate when deploying Python web APIs in containers. The update adds built-in health checks and configuration through environment variables. Early users reported shorter setup times. Documentation includes Docker examples."),
    ],
    "science": [
        ("Space agency tests reusable lunar lander engine", "Engineers completed a series of test firings for an engine intended for a reusable lunar lander. The tests evaluated restart capability and thermal performance. Further trials are scheduled before a full system test. The programme aims to support long-term space exploration."),
        ("Telescope captures detailed images of distant galaxy cluster", "Astronomers released images of a distant galaxy cluster showing gravitational lensing. The data will help researchers study dark matter distribution. The observations were made in infrared wavelengths. Scientists plan follow-up spectroscopy."),
        ("Researchers map climate impact on monsoon rainfall", "A climate study analysed decades of rainfall records to understand changes in monsoon patterns. The researchers found increased variability in several regions. They used statistical models combined with satellite data. The authors call for improved local forecasting."),
        ("Battery recycling method recovers more lithium", "Chemists described a recycling process that recovers a higher share of lithium from used batteries. The method uses lower temperatures than conventional approaches. The team is working with industry on pilot plants. Recycling could reduce pressure on mining."),
    ],
    "business": [
        ("Startups adopt AI assistants for customer support", "Small companies are increasingly using AI assistants to answer routine customer questions. Owners report faster response times but stress the need for human review. Analysts note concerns about accuracy and data privacy. Adoption is highest in e-commerce."),
        ("Renewable energy investment rises in the region", "Investment in solar and wind projects increased over the past year according to an industry report. Lower equipment costs and supportive policy were cited as reasons. Grid storage remains a bottleneck. Several new projects were announced this quarter."),
        ("Fintech firms focus on fraud prevention", "Financial technology companies are investing in fraud detection systems that analyse transaction patterns. Machine learning models flag unusual activity for review. Regulators encourage transparent decision making. Customers are being educated about common scams."),
    ],
    "sports": [
        ("National cricket team announces squad for upcoming series", "Selectors named a squad that includes three uncapped players. The coach said the series is a chance to test bench strength. Training camps begin next week. The first match is scheduled at the end of the month."),
        ("Marathon organisers introduce sustainability measures", "Organisers of a city marathon announced reusable cups and better waste sorting. Volunteers will guide runners at recycling points. The event expects record participation. Registration closes soon."),
    ],
}

def build(category, items, start):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           f"<title>Sample {category.title()} News (synthetic)</title>", "<link>https://example.com/</link>",
           "<description>Synthetic demo feed generated for offline use. Not real news.</description>"]
    for n, (title, body) in enumerate(items):
        slug = title.lower().replace(" ", "-")[:60]
        out.append("<item>")
        out.append(f"<title>{escape(title)}</title>")
        out.append(f"<link>https://example.com/{category}/{slug}</link>")
        out.append(f"<description>{escape(body)}</description>")
        out.append(f"<pubDate>{format_datetime(start - timedelta(hours=5 * n))}</pubDate>")
        out.append("</item>")
    out.append("</channel></rss>")
    return "\n".join(out)

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "data" / "sample_feeds"
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    for cat, items in STORIES.items():
        (root / f"{cat}.xml").write_text(build(cat, items, now), encoding="utf-8")
        print("wrote", cat)
