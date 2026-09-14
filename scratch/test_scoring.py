import re
import urllib.parse

INVALID_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
    '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf', '.eot'
)

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')

DANISH_LEGAL_SUFFIXES = [
    r'\ba/s\b', r'\baps\b', r'\bi/s\b', r'\bk/s\b', r'\bp/s\b',
    r'\bs\.m\.b\.a\.\b', r'\bsmba\b', r'\ba\.m\.b\.a\.\b', r'\bamba\b',
    r'\bf\.m\.b\.a\.\b', r'\bfmba\b', r'\bholding\b', r'\bgroup\b',
    r'\bdenmark\b', r'\bdanmark\b', r'\bdk\b', r'\baktielselskab\b',
    r'\banpartsselskab\b', r'\bfilial\b', r'\beurope\b', r'\bnordic\b'
]

def extract_clean_domain(url):
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(('http://', 'https://')):
        u = 'https://' + u
    try:
        parsed = urllib.parse.urlparse(u)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return netloc.split(':')[0].strip()
    except Exception:
        return ""

def extract_sld(domain_or_url):
    if not domain_or_url:
        return ''
    d = domain_or_url.strip().lower()
    if '://' in d:
        try:
            d = urllib.parse.urlparse(d).netloc
        except Exception:
            pass
    if d.startswith('www.'):
        d = d[4:]
    d = d.split(':')[0]
    parts = d.split('.')
    if len(parts) >= 2:
        if len(parts) >= 3 and parts[-2] in ['co', 'com', 'org', 'net', 'edu', 'gov']:
            return parts[-3]
        return parts[-2]
    return parts[0]

def extract_brand_tokens(company_name):
    if not company_name:
        return set()
    p = company_name.lower()
    for s in DANISH_LEGAL_SUFFIXES:
        p = re.sub(s, ' ', p, flags=re.IGNORECASE)
    p = re.sub(r'[^a-z0-9æøå\s]', ' ', p)
    tokens = {w for w in p.split() if len(w) >= 3}
    return tokens

JUNK_EMAIL_DOMAINS = {
    'cookieinformation.com', 'cookieinformation.dk', 'cookiebot.com', 'cybot.com',
    'onetrust.com', 'usercentrics.com', 'usercentrics.eu', 'termly.io',
    'iubenda.com', 'trustarc.com', 'complianz.io', 'civicuk.com', 'quantcast.com',
    'didomi.io', 'didomi.com', 'osano.com', 'securiti.ai', 'kunden.de',
    'datanyze.com', 'leadiq.com', 'zoominfo.com', 'lusha.com', 'apollo.io',
    'rocketreach.co', 'signalhire.com', 'selskabsinfo.dk', 'proff.dk', 'krak.dk',
    'biq.dk', 'cvr.dk', 'virk.dk', 'degulesider.dk', 'dnb.com', 'kompass.com',
    'yellowpages.dk', 'yellowpages.com', 'yelp.dk', 'yelp.com', 'trustpilot.com',
    'opencorporates.com', 'b2bhint.com', 'cybo.com', 'infobel.com', 'firmania.dk',
    'uni2study.com', 'prodenmark.com', 'feve.org',
    'acmecorporation.com', 'example.com', 'example.org', 'example.net', 'example.dk',
    'domain.com', 'yourdomain.com', 'yoursite.com', 'mycompany.com', 'company.com',
    'companyname.com', 'placeholder.com', 'test.com', 'sample.com', 'email.com',
    'mail.com', 'themetrust.com', 'templatemonster.com', 'themeforest.net', 'envato.com',
    'wixpress.com', 'wix.com', 'squarespace.com', 'weebly.com', 'shopify.com',
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'webador.com', 'one.com',
    'godaddy.com', 'wordpress.com', 'bluepillow.com', 'booking.com', 'tripadvisor.com',
    'google.com', 'facebook.com', 'instagram.com', 'schema.org', 'w3.org'
}

JUNK_PREFIXES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'cookie',
    'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon',
    'postmaster', 'example', 'muster', 'dpo', 'test', 'dataprotection',
    'dataprotectionoffice', 'datenschutz', 'kundeservice-noreply'
}

PREFERRED_USERNAMES = {
    'info', 'kontakt', 'contact', 'kontor', 'mail', 'post', 'office',
    'salg', 'sales', 'support', 'service', 'job', 'hr', 'karriere', 'career',
    'kundeservice', 'admin', 'ordre', 'order', 'hovedkontor'
}

def clean_single_email(raw_email):
    if not raw_email:
        return ''
    s = str(raw_email).strip()
    try:
        s = urllib.parse.unquote(s)
    except Exception:
        pass
    for prefix in ['mailto:', 'u003e', 'u003c', '&lt;', '&gt;', ':', ' ']:
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    s = s.replace('%20', '').replace('%2520', '').replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '').strip()
    s = s.strip("'\"<>[](),;")
    if '@' not in s:
        return ''
    parts = s.split('@')
    if len(parts) != 2:
        return ''
    local_part, domain = parts[0].strip().lower(), parts[1].strip().lower()
    local_part = re.sub(r'^[^\w]+|[^\w]+$', '', local_part)
    domain = re.sub(r'^[^\w]+|[^\w]+$', '', domain)
    if not local_part or not domain or '.' not in domain:
        return ''
    if any(domain.endswith(ext) for ext in INVALID_EXTENSIONS):
        return ''
    if re.search(r'@\d+\.\d+', s) or re.search(r'\.\d+$', domain):
        return ''
    if any(domain.endswith('.' + ext) for ext in ['js', 'ts', 'css', 'json', 'map', 'min', 'esm', 'mjs']):
        return ''
    clean_email = f'{local_part}@{domain}'
    if not EMAIL_REGEX.match(clean_email):
        return ''
    if any(jp in local_part for jp in JUNK_PREFIXES):
        return ''
    for jd in JUNK_EMAIL_DOMAINS:
        if domain == jd or domain.endswith('.' + jd):
            return ''
    return clean_email

def score_email_new(email, site_url='', company_name=''):
    if not email:
        return 0
    clean = clean_single_email(email)
    if not clean:
        return 0
    username, domain = clean.split('@', 1)
    site_sld = extract_sld(site_url)
    email_sld = extract_sld(domain)
    brand_tokens = extract_brand_tokens(company_name)

    is_same_brand_domain = (site_sld and email_sld == site_sld) or (email_sld in brand_tokens)
    is_brand_username = any(b in username for b in brand_tokens)

    if is_same_brand_domain:
        if is_brand_username:
            return 250
        if username in PREFERRED_USERNAMES:
            return 230
        return 200

    is_partial_brand = (site_sld and (site_sld in email_sld or email_sld in site_sld)) or any(b in email_sld for b in brand_tokens)
    if is_partial_brand:
        if username in PREFERRED_USERNAMES or is_brand_username:
            return 180
        return 150

    clean_site_domain = extract_clean_domain(site_url)
    if clean_site_domain and (domain == clean_site_domain or domain.endswith('.' + clean_site_domain)):
        if username in PREFERRED_USERNAMES:
            return 140
        return 120

    if domain in {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'live.com'}:
        if is_brand_username or username in PREFERRED_USERNAMES:
            return 50
        return 35

    return 0

emails_test = [
    ('dinex@dinex.dk', 'https://www.dinex.net/', 'Dinex A/S'),
    ('info@cookieinformation.com', 'https://www.dinex.net/', 'Dinex A/S'),
    ('htmx.org@2.0.4', 'https://www.dinex.net/', 'Dinex A/S'),
    ('alpinejs@3.14.8.js', 'https://www.dinex.net/', 'Dinex A/S'),
    ('info@dinex.net', 'https://www.dinex.net/', 'Dinex A/S'),
    ('sales@dinex.com', 'https://www.dinex.net/', 'Dinex A/S'),
    ('emma@acmecorporation.com', 'http://www.aldautomotive.co.uk/', 'ALD Automotive A/S'),
    ('contact@aldautomotive.com', 'http://www.aldautomotive.co.uk/', 'ALD Automotive A/S'),
    ('info@datanyze.com', 'https://www.datanyze.com', 'Bankernes EDB Central A.M.B.A.'),
    ('kontakt@novonordisk.com', 'https://selskabsinfo.dk', 'Cassin Networks ApS'),
]

for em, site, comp in emails_test:
    sc = score_email_new(em, site, comp)
    print(f'{em:30} | {site:30} | {comp:28} -> Score: {sc}')
