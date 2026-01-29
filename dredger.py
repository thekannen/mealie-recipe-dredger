import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory
import json
import time
import os
import random
import re
import logging
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv

# --- LOAD ENV VARS ---
load_dotenv()

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("dredger")

# --- CONFIGURATION ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
SCRAPE_LANG = os.getenv('SCRAPE_LANG', 'en')
TARGET_RECIPES_PER_SITE = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
SCAN_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))

# 🧠 MEMORY SETTINGS
os.makedirs("data", exist_ok=True)
REJECT_FILE = "data/rejects.json"
IMPORTED_FILE = "data/imported.json"
DetectorFactory.seed = 0 

# --- CURATED SOURCES (The Full List) ---
ENV_SITES = os.getenv('SITES', '')
if ENV_SITES:
    SITES = [s.strip() for s in ENV_SITES.split(',') if s.strip()]
else:
    SITES = [
        # --- GENERAL / WESTERN ---
        "https://www.seriouseats.com", "https://www.bonappetit.com",
        "https://www.foodandwine.com", "https://www.simplyrecipes.com",
        "https://smittenkitchen.com", "https://www.skinnytaste.com",
        "https://www.budgetbytes.com", "https://www.twopeasandtheirpod.com",
        "https://cookieandkate.com", "https://minimalistbaker.com",
        "https://gimmesomeoven.com", "https://pinchofyum.com",
        "https://www.loveandlemons.com", "https://damndelicious.net",
        "https://www.halfbakedharvest.com", "https://sallysbakingaddiction.com",
        "https://www.wellplated.com", "https://www.acouplecooks.com",
        "https://www.feastingathome.com", "https://www.recipetineats.com",
        "https://www.dinneratthezoo.com", "https://cafedelites.com",
        "https://natashaskitchen.com", "https://www.spendwithpennies.com",
        "https://carlsbadcravings.com", "https://www.averiecooks.com",
        "https://www.closetcooking.com", "https://rasamalaysia.com",
        "https://iamafoodblog.com", "https://www.101cookbooks.com",
        "https://www.sproutedkitchen.com", "https://www.howsweeteats.com",
        "https://joythebaker.com", "https://www.melskitchencafe.com",
        "https://www.ambitiouskitchen.com", "https://www.eatingbirdfood.com",

        # --- ASIAN (East, SE, South) ---
        "https://www.justonecookbook.com", "https://www.woksoflife.com",
        "https://omnivorescookbook.com", "https://glebekitchen.com",
        "https://www.indianhealthyrecipes.com", "https://www.vegrecipesofindia.com",
        "https://www.manjulaskitchen.com", "https://hebbarskitchen.com",
        "https://maangchi.com", "https://www.koreanbapsang.com",
        "https://mykoreankitchen.com", "https://hot-thai-kitchen.com",
        "https://sheasim.com", "https://panlasangpinoy.com",
        "https://www.kawalingpinoy.com", "https://steamykitchen.com",
        "https://chinasichuanfood.com", "https://redhousespice.com",
        "https://seonkyounglongest.com", "https://pupswithchopsticks.com",
        "https://wandercooks.com", "https://www.pressurecookrecipes.com",

        # --- LATIN AMERICAN ---
        "https://www.mexicoinmykitchen.com", "https://www.isabeleats.com",
        "https://pinaenlacocina.com", "https://www.dominicancooking.com",
        "https://www.mycolombianrecipes.com", "https://www.laylita.com",
        "https://www.braziliankitchenabroad.com", "https://www.chilipeppermadness.com",
        "https://www.kitchengidget.com", "https://www.quericavida.com",

        # --- AFRICAN / CARIBBEAN ---
        "https://www.africanbites.com", "https://lowcarbafrica.com",
        "https://www.myactivekitchen.com", "https://9jafoodie.com",
        "https://www.cheflolaskitchen.com", "https://sisijemimah.com",
        "https://originalflava.com", "https://caribbeanpot.com",
        "https://www.alicaspepperpot.com", "https://jehancancook.com",
        "https://www.cookwithdena.com", "https://kausarskitchen.com",

        # --- MEDITERRANEAN / MIDDLE EASTERN ---
        "https://www.themediterraneandish.com", "https://cookieandkate.com",
        "https://www.lazycatkitchen.com", "https://ozlemsturkishtable.com",
        "https://persianmama.com", "https://www.unicornsinthekitchen.com",
        "https://www.myjewishlearning.com/the-nosher", "https://toriavey.com",

        # --- BAKING / DESSERT SPECIFIC ---
        "https://www.kingarthurbaking.com/recipes", "https://preppykitchen.com",
        "https://sugarspunrun.com", "https://www.biggerbolderbaking.com"
    ]

# --- PARANOID FILTERS ---
LISTICLE_REGEX = re.compile(r'(\d+)-(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)
BAD_KEYWORDS = ["roundup", "collection", "guide", "review", "giveaway", "shop", "store", "product"]

# --- UTILS ---
def load_json_set(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: return set(json.load(f))
        except: return set()
    return set()

def save_json_set(filename, data_set):
    with open(filename, 'w') as f: json.dump(list(data_set), f)

REJECTS = load_json_set(REJECT_FILE)
IMPORTED = load_json_set(IMPORTED_FILE)

# --- ROBUST SESSION (From your script) ---
def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session

def is_paranoid_skip(url, soup=None):
    try:
        path = urlparse(url).path
        slug = path.strip("/").split("/")[-1].lower()
        if LISTICLE_REGEX.search(slug): return f"Listicle detected in URL: {slug}"
        for kw in BAD_KEYWORDS:
            if kw in slug: return f"Bad keyword in URL: {kw}"
        if soup:
            title = soup.title.string.lower() if soup.title else ""
            if "best recipes" in title or "top 10" in title: return "Listicle title detected"
    except: pass
    return False

# --- INTELLIGENT SITEMAP FINDER (From your script) ---
def get_sitemap_from_robots(session, base_url):
    try:
        r = session.get(f"{base_url}/robots.txt", timeout=5)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if "Sitemap:" in line:
                    return line.split("Sitemap:")[1].strip()
    except Exception: return None

def find_sitemap(session, base_url):
    # 1. Check Robots.txt
    robots_sitemap = get_sitemap_from_robots(session, base_url)
    if robots_sitemap: 
        logger.debug(f"   🤖 Found sitemap in robots.txt: {robots_sitemap}")
        return robots_sitemap
    
    # 2. Check Standard Candidates
    candidates = [
        f"{base_url}/sitemap_index.xml", f"{base_url}/sitemap.xml",
        f"{base_url}/wp-sitemap.xml", f"{base_url}/post-sitemap.xml",
        f"{base_url}/recipe-sitemap.xml"
    ]
    
    for url in candidates:
        try:
            r = session.head(url, timeout=5)
            if r.status_code == 200:
                logger.debug(f"   🔍 Found standard sitemap: {url}")
                return url
        except Exception: pass
    return None

# --- RECURSIVE SITEMAP PARSING (Enhanced) ---
def fetch_sitemap_urls(session, url, depth=0):
    if depth > 2: return []
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200: return []
        
        # Use lxml for speed if available, fallback to regex for simple parsing
        if '<sitemap>' in r.text[:5000]:
            logger.debug(f"   📂 Parsing Index (Depth {depth}): {url}")
            sub_maps = re.findall(r'<loc>(https?://[^<]+)</loc>', r.text)
            
            # Smart filter: prioritize recipe/post sitemaps
            targets = [s for s in sub_maps if 'post' in s or 'recipe' in s]
            if not targets: targets = sub_maps
            
            all_urls = []
            for sub in targets[:3]: # Limit 3
                all_urls.extend(fetch_sitemap_urls(session, sub, depth + 1))
            return all_urls
        else:
            return re.findall(r'<loc>(https?://[^<]+)</loc>', r.text)
    except Exception as e:
        logger.warning(f"Sitemap parse error {url}: {e}")
        return []

# --- ROBUST RECIPE VERIFICATION (From your script) ---
def verify_and_scrape_recipe(url, session):
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200: return None
        
        # 1. Language Check (Fastest)
        try:
            lang = detect(r.text[:2000])
            if SCRAPE_LANG not in lang and 'en' not in SCRAPE_LANG:
                logger.debug(f"   Skipping language {lang}: {url}")
                return None
        except: pass

        # 2. Recipe Detection
        is_recipe = False
        
        # A. JSON-LD Check
        if '"@type":"Recipe"' in r.text or '"@type": "Recipe"' in r.text: 
            is_recipe = True
        
        # B. CSS Class Fallback (If no JSON-LD)
        if not is_recipe:
            soup = BeautifulSoup(r.content, 'lxml')
            if soup.find(class_=lambda x: x and ('wp-recipe-maker' in x or 'tasty-recipes' in x or 'mv-create-card' in x)):
                is_recipe = True
        
        if is_recipe:
            # Paranoid Check
            soup = BeautifulSoup(r.content, 'lxml') # Ensure we have soup
            reason = is_paranoid_skip(url, soup)
            if reason:
                logger.warning(f"🛡️  Paranoid Skip ({reason}): {url}")
                return None
            return True # Valid recipe!
            
    except Exception as e:
        logger.error(f"❌ Scraping error on {url}: {e}")
    return None

# --- IMPORT LOGIC ---
def import_to_mealie(session, url):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would import: {url}")
        return True
    
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    try:
        r = session.post(f"{MEALIE_URL}/api/recipes/create-url", headers=headers, json={"url": url}, timeout=20)
        if r.status_code == 201:
            logger.info(f"✅ [Mealie] Imported: {url}")
            return True
        elif r.status_code == 409:
            logger.info(f"⚠️ [Mealie] Duplicate: {url}")
            return True 
        else:
            logger.error(f"❌ [Mealie] Failed ({r.status_code}): {url}")
    except Exception as e:
        logger.error(f"❌ [Mealie] Connection Error: {e}")
    return False

def import_to_tandoor(session, url):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would import to Tandoor: {url}")
        return True
    
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
    try:
        r = session.post(f"{TANDOOR_URL}/api/recipe/import-url/", headers=headers, json={"url": url}, timeout=20)
        if r.status_code in [200, 201]:
            logger.info(f"✅ [Tandoor] Imported: {url}")
            return True
        else:
            logger.error(f"❌ [Tandoor] Failed ({r.status_code}): {url}")
    except Exception as e:
        logger.error(f"❌ [Tandoor] Connection Error: {e}")
    return False

# --- MAIN LOOP ---
def process_site(site_url):
    logger.info(f"🌍 Processing Site: {site_url}")
    session = get_session()
    
    # 1. Intelligent Sitemap Discovery
    sitemap_url = find_sitemap(session, site_url)
    if not sitemap_url:
        logger.warning(f"⚠️ No sitemap found for {site_url}")
        return

    # 2. Recursive Parsing
    urls = fetch_sitemap_urls(session, sitemap_url)
    if not urls:
        logger.warning(f"⚠️ No usable URLs found in sitemaps for {site_url}")
        return

    logger.info(f"   Found {len(urls)} candidates.")
    random.shuffle(urls)
    
    count = 0
    for url in urls[:SCAN_DEPTH]:
        if count >= TARGET_RECIPES_PER_SITE: break
        if url in IMPORTED or url in REJECTS: continue
        
        # 3. Robust Verification
        if verify_and_scrape_recipe(url, session):
            success = False
            if MEALIE_ENABLED: success = import_to_mealie(session, url)
            if TANDOOR_ENABLED: success = import_to_tandoor(session, url) or success
            
            if success:
                IMPORTED.add(url)
                count += 1
                time.sleep(2)
        else:
            logger.debug(f"   No recipe found: {url}")
            REJECTS.add(url)

if __name__ == "__main__":
    logger.info("🍲 Recipe Dredger Started (Enhanced Edition)")
    logger.info(f"   Mode: {'DRY RUN' if DRY_RUN else 'LIVE IMPORT'}")
    
    random.shuffle(SITES)
    for site in SITES:
        process_site(site)
        save_json_set(REJECT_FILE, REJECTS)
        save_json_set(IMPORTED_FILE, IMPORTED)
        
    logger.info("🏁 Dredge Cycle Complete.")
