# -*- coding: utf-8 -*-
import re
import urllib.parse

LEGAL_FORMS_FI = ['oy', 'ab', 'oyj', 'ky', 'ay', 'tmi', 'osk', 'ry', 'ltd']

EXCLUDED_PLATFORMS_FI = {
    # Danh bạ, cổng thông tin doanh nghiệp, tra cứu mã số thuế Phần Lan
    'finder.fi', 'profinder.fi', 'kauppalehti.fi', 'asiakastieto.fi', 'yritystele.fi', 'proff.fi',
    'fonecta.fi', 'fonecta.com', 'suomi.fi', 'prh.fi', 'ytj.fi', 'vero.fi',
    'yritysopas.fi', 'yrityshaku.fi', 'yritykset.fi', 'yritysfakta.fi', 'taloustutka.fi',
    'almamedia.fi', 'directa.fi', 'eniro.fi', 'eniro.se', '0100100.fi', 'sinunyritys.fi',
    'suomenyritykset.fi', 'suomenyrityshaku.fi', 'yritysrekisteri.fi', 'bisnode.fi',
    'bisnode.com', 'dnb.com', 'kompass.com', 'europages.com', 'infobel.com',
    'firmaspraak.fi', 'tietopalvelut.fi', 'avointieto.fi', 'tulli.fi', 'finder.fi',

    # Tuyển dụng, việc làm, sàn trung gian, rao vặt
    'duunitori.fi', 'oikotie.fi', 'monster.fi', 'jobly.fi', 'tyomarkkinatori.fi',
    'te-palvelut.fi', 'tori.fi', 'indeed.com', 'glassdoor.com', 'glassdoor.fi',
    'jooble.org', 'stepstone.se', 'stepstone.de', 'rekrytointi.com', 'uranus.fi',
    'workinfinland.com', 'cv-online.com', 'linkedin.com', 'staffpoint.fi', 'barona.fi',
    'eezy.fi', 'bolt.works', 'vmp.fi', 'adecco.fi', 'manpower.fi',
    
    # Mạng xã hội & Video/Audio
    'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com', 'youtube.com',
    'tiktok.com', 'pinterest.com', 'wikipedia.org', 'reddit.com', 'vimeo.com',
    
    # Báo chí, truyền thông, diễn đàn Phần Lan
    'yle.fi', 'is.fi', 'hs.fi', 'iltalehti.fi', 'uusisuomi.fi', 'talouselama.fi',
    'tivi.fi', 'tekniikkatalous.fi', 'mtv.fi', 'mtvuutiset.fi', 'suomi24.fi',
    'vauva.fi', 'helsinginuutiset.fi', 'tamperelainen.fi', 'turkulainen.fi',
    'aamulehti.fi', 'kaleva.fi', 'ksml.fi', 'savonsanomat.fi', 'ess.fi',
    'satakunnankansa.fi', 'lapinkansa.fi', 'karjalainen.fi', 'pohjalainen.fi',
    'leadfeeder.com', 'tripadvisor.com', 'trustpilot.com', 'google.com', 'google.fi',
    'bing.com', 'duckduckgo.com', 'yahoo.com', 'msn.com',
    
    # Nền tảng tạo web / blog miễn phí không có tên miền riêng (nếu là trang chủ nền tảng)
    'wix.com', 'wixsite.com', 'wordpress.com', 'wordpress.org', 'weebly.com', 'squarespace.com',
    'shopify.com', 'myshopify.com', 'site123.me', 'jimdosite.com', 'webnode.fi', 'webnode.com',
    'blogspot.com', 'medium.com', 'github.io', 'sites.google.com'
}

PLATFORM_KEYWORDS_FI = {
    'directory', 'yellowpages', 'yrityshaku', 'rekry', 'tyopaikat', 'duunit',
    'katalog', 'listing', 'yritykset', 'portaali', 'portal', 'rekisteri',
    'tietokanta', 'uutiset', 'media', 'sanomat', 'lehti', 'forum', 'keskustelu',
    'arvostelut', 'reviews', 'ratings'
}

GENERIC_NAME_TOKENS = {
    'suomi', 'finland', 'palvelut', 'palvelu', 'group', 'nordic', 'holding', 
    'consulting', 'management', 'international', 'services', 'service', 'team', 
    'staff', 'work', 'works', 'yhtio', 'partner', 'partners', 'henkilosto', 'rekrytointi'
}

def clean_company_name_fi(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', name).strip().lower()
    tokens = n.split()
    tokens = [t for t in tokens if t not in LEGAL_FORMS_FI]
    return ' '.join(tokens).strip()

def normalize_fi_domain_token(text):
    """Chuyển đổi ký tự tiếng Phần Lan ä->a, ö->o, å->a để so khớp với domain ASCII"""
    t = text.lower()
    t = t.replace('ä', 'a').replace('ö', 'o').replace('å', 'a')
    return re.sub(r'[^a-z0-9]', '', t)

def is_strictly_company_domain_fi(domain, company_name):
    """
    Kiểm tra tên miền có thực sự là WEB RIÊNG CỦA DOANH NGHIỆP hay không:
    - Loại bỏ 100% các trang nền tảng, danh bạ, trang đăng tin tuyển dụng, mạng xã hội, báo chí.
    - Bắt buộc domain phải chứa từ khóa nhận diện đặc thù của thương hiệu công ty.
    """
    if not domain:
        return False
    d = domain.lower().replace('www.', '').strip()
    
    # 1. Trực tiếp nằm trong danh sách đen các nền tảng/danh bạ
    for plat in EXCLUDED_PLATFORMS_FI:
        if d == plat or d.endswith('.' + plat):
            return False
            
    q_clean = clean_company_name_fi(company_name)
    tokens = q_clean.split()
    
    # 2. Kiểm tra từ khóa nền tảng/danh bạ (chỉ cấm nếu từ khóa đó không nằm trong tên cty)
    for kw in PLATFORM_KEYWORDS_FI:
        if kw in d and kw not in q_clean:
            return False
            
    # 3. Phải chứa từ khóa thương hiệu đặc trưng của công ty
    # Lọc ra các từ đặc trưng (độ dài >= 3 và không phải từ quá chung chung)
    distinctive_tokens = [t for t in tokens if len(t) >= 3 and t not in GENERIC_NAME_TOKENS]
    
    # Chuyển đổi sang dạng ASCII không dấu để so sánh với domain
    d_clean = re.sub(r'[^a-z0-9]', '', d.split('.')[0]) # chỉ lấy tên chính của domain
    
    if distinctive_tokens:
        for t in distinctive_tokens:
            t_norm = normalize_fi_domain_token(t)
            if len(t_norm) >= 3 and (t_norm in d or t_norm in d_clean):
                return True
            
    # Nếu toàn từ thông dụng (vd: Nordic Staff Oy -> tokens: nordic, staff)
    clean_nospace = ''.join(normalize_fi_domain_token(t) for t in tokens)
    if len(clean_nospace) >= 5 and clean_nospace in d:
        return True
        
    # Ghép 2 từ đầu
    if len(tokens) >= 2:
        combo = normalize_fi_domain_token(tokens[0]) + normalize_fi_domain_token(tokens[1])
        if len(combo) >= 5 and combo in d:
            return True
            
    return False

# Test cases
test_cases = [
    # (Company, candidate domain, expected)
    ("Järvimäki HR Services Oy", "jarvimaki.fi", True),
    ("Järvimäki HR Services Oy", "jarvimakihr.fi", True),
    ("Järvimäki HR Services Oy", "asiakastieto.fi", False),
    ("Järvimäki HR Services Oy", "duunitori.fi", False),
    ("Järvimäki HR Services Oy", "finder.fi", False),
    ("Järvimäki HR Services Oy", "facebook.com", False),
    ("Järvimäki HR Services Oy", "services.fi", False), # generic token only
    ("Järvimäki HR Services Oy", "yritystele.fi", False),
    ("Kiiskinen Consulting Oy", "kiiskinen.fi", True),
    ("Kiiskinen Consulting Oy", "kiiskinenconsulting.fi", True),
    ("Kiiskinen Consulting Oy", "consulting.fi", False),
    ("Kiiskinen Consulting Oy", "kauppalehti.fi", False),
    ("DuuniSawo Oy", "duunisawo.fi", True),
    ("DuuniSawo Oy", "duunitori.fi", False),
    ("KeyStaff Oy", "keystaff.fi", True),
    ("Ideal Scouting Oy", "idealscouting.com", True),
    ("Kiiskinen Consulting Oy", "finder.fi", False),
    ("Kiiskinen Consulting Oy", "profinder.fi", False),
    ("Kiiskinen Consulting Oy", "b2b.profinder.fi", False),
    ("Kont Invest Oy", "b2b.profinder.fi", False),
    ("Kont Invest Oy", "profinder.fi", False),
    ("Kont Invest Oy", "finder.fi", False),
    ("Kont Invest Oy", "kontinvest.fi", True),
]

all_passed = True
for comp, dom, expected in test_cases:
    actual = is_strictly_company_domain_fi(dom, comp)
    res = "PASS" if actual == expected else "FAIL"
    if actual != expected:
        all_passed = False
    print(f"[{res}] {comp} -> {dom} | Expected: {expected} | Actual: {actual}")

print(f"\nResult: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
