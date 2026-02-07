"""
Recipe Dredger - Enhanced Public Edition
Intelligent recipe scraper for Mealie/Tandoor with optimized performance and reliability.
Usage: python3 dredger.py [--dry-run] [--limit 10] [--sites my_sites.json] [--no-cache] [--version]
"""

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
import argparse
import signal
from urllib.parse import urlparse
from dotenv import load_dotenv
from typing import Optional, Set, List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

# --- CONSTANTS ---
VERSION = "1.0.0-beta.9"

# --- OPTIONAL VISUALS ---
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

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

# --- CONFIGURATION DEFAULTS ---
DEFAULT_TARGET = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
DEFAULT_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'

# --- PLATFORM SETTINGS ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

# Rate limiting
DEFAULT_CRAWL_DELAY = float(os.getenv('CRAWL_DELAY', 2.0))
RESPECT_ROBOTS_TXT = os.getenv('RESPECT_ROBOTS_TXT', 'true').lower() == 'true'

# Memory settings
os.makedirs("data", exist_ok=True)
REJECT_FILE = "data/rejects.json"
IMPORTED_FILE = "data/imported.json"
RETRY_FILE = "data/retry_queue.json"
STATS_FILE = "data/stats.json"
SITEMAP_CACHE_FILE = "data/sitemap_cache.json"
CACHE_EXPIRY_DAYS = int(os.getenv('CACHE_EXPIRY_DAYS', 7))

DetectorFactory.seed = 0

# --- THE FULL CURATED LIST ---
DEFAULT_SITES = [
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

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class RecipeCandidate:
    url: str
    priority: int = 0 
    
    def __hash__(self):
        return hash(self.url)
    
    def __eq__(self, other):
        return self.url == other.url if isinstance(other, RecipeCandidate) else self.url == other

@dataclass
class SiteStats:
    site_url: str
    recipes_found: int = 0
    recipes_imported: int = 0
    recipes_rejected: int = 0
    errors: int = 0
    last_run: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)

# ============================================================================
# PERSISTENT STORAGE MANAGER
# ============================================================================

class StorageManager:
    def __init__(self):
        self.rejects: Set[str] = self._load_json_set(REJECT_FILE)
        self.imported: Set[str] = self._load_json_set(IMPORTED_FILE)
        self.retry_queue: Dict[str, dict] = self._load_json_dict(RETRY_FILE)
        self.stats: Dict[str, dict] = self._load_json_dict(STATS_FILE)
        self.sitemap_cache: Dict[str, dict] = self._load_json_dict(SITEMAP_CACHE_FILE)
        
        self._changes_since_flush = 0
        self._flush_threshold = 50
        
    def _load_json_set(self, filename: str) -> Set[str]:
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.warning(f"Error loading {filename}: {e}")
        return set()
    
    def _load_json_dict(self, filename: str) -> dict:
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {filename}: {e}")
        return {}
    
    def _save_json_set(self, filename: str, data_set: Set[str]):
        with open(filename, 'w') as f:
            json.dump(list(data_set), f, indent=2)
    
    def _save_json_dict(self, filename: str, data_dict: dict):
        with open(filename, 'w') as f:
            json.dump(data_dict, f, indent=2)
    
    def add_imported(self, url: str):
        self.imported.add(url)
        self._changes_since_flush += 1
        self._auto_flush()
    
    def add_reject(self, url: str):
        self.rejects.add(url)
        self._changes_since_flush += 1
        self._auto_flush()
    
    def add_retry(self, url: str, reason: str):
        self.retry_queue[url] = {
            'reason': reason,
            'attempts': 0,
            'last_attempt': datetime.now().isoformat()
        }
        self._changes_since_flush += 1
        self._auto_flush()
    
    def update_stats(self, site_url: str, stats: SiteStats):
        self.stats[site_url] = stats.to_dict()
        self._changes_since_flush += 1
        self._auto_flush()
    
    def get_cached_sitemap(self, site_url: str) -> Optional[dict]:
        if site_url not in self.sitemap_cache: 
            return None
        
        cache_entry = self.sitemap_cache[site_url]
        cached_time = datetime.fromisoformat(cache_entry['timestamp'])
        
        if datetime.now() - cached_time > timedelta(days=CACHE_EXPIRY_DAYS):
            return None
        
        return cache_entry
    
    def cache_sitemap(self, site_url: str, sitemap_url: str, urls: List[str]):
        self.sitemap_cache[site_url] = {
            'sitemap_url': sitemap_url,
            'urls': urls,
            'timestamp': datetime.now().isoformat()
        }
        self._changes_since_flush += 1
        self._auto_flush()
    
    def _auto_flush(self):
        if self._changes_since_flush >= self._flush_threshold:
            self.flush_all()
    
    def flush_all(self):
        self._save_json_set(REJECT_FILE, self.rejects)
        self._save_json_set(IMPORTED_FILE, self.imported)
        self._save_json_dict(RETRY_FILE, self.retry_queue)
        self._save_json_dict(STATS_FILE, self.stats)
        self._save_json_dict(SITEMAP_CACHE_FILE, self.sitemap_cache)
        self._changes_since_flush = 0

# ============================================================================
# GRACEFUL KILLER
# ============================================================================

class GracefulKiller:
    """Catches Docker stop signals to allow safe shutdown."""
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        signal_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (Docker Stop)'
        logger.info(f"🛑 Received {signal_name}. Initiating graceful shutdown...")
        self.kill_now = True

# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    def __init__(self):
        self.last_request: Dict[str, float] = {}
        self.crawl_delays: Dict[str, float] = {}
        self.session = get_session()
    
    def get_domain(self, url: str) -> str:
        return urlparse(url).netloc
    
    def get_crawl_delay(self, domain: str) -> float:
        if domain in self.crawl_delays:
            return self.crawl_delays[domain]
        
        delay = DEFAULT_CRAWL_DELAY
        if RESPECT_ROBOTS_TXT:
            try:
                r = self.session.get(f"https://{domain}/robots.txt", timeout=5)
                if r.status_code == 200:
                    for line in r.text.splitlines():
                        if line.lower().startswith('crawl-delay:'):
                            try:
                                delay = float(line.split(':')[1].strip())
                                break
                            except ValueError: 
                                pass
            except Exception: 
                pass
        
        self.crawl_delays[domain] = delay
        return delay
    
    def wait_if_needed(self, url: str):
        domain = self.get_domain(url)
        delay = self.get_crawl_delay(domain)
        
        if domain in self.last_request:
            elapsed = time.time() - self.last_request[domain]
            if elapsed < delay:
                # Add jitter (0.5x to 1.5x) to mimic human variance
                jitter = random.uniform(0.5, 1.5)
                sleep_time = (delay - elapsed) * jitter
                time.sleep(sleep_time)
        
        self.last_request[domain] = time.time()

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def get_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3, 
        backoff_factor=1, 
        status_forcelist=[500, 502, 503, 504, 429],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) RecipeDredger/{VERSION}'
    })
    return session

# ============================================================================
# SITEMAP CRAWLER
# ============================================================================

class SitemapCrawler:
    def __init__(self, session: requests.Session, storage: StorageManager):
        self.session = session
        self.storage = storage
    
    def find_sitemap(self, base_url: str) -> Optional[str]:
        # 1. Check robots.txt
        try:
            r = self.session.get(f"{base_url}/robots.txt", timeout=5)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if "Sitemap:" in line:
                        return line.split("Sitemap:")[1].strip()
        except: 
            pass
        
        # 2. Check standard candidates
        candidates = [
            f"{base_url}/sitemap_index.xml", 
            f"{base_url}/sitemap.xml",
            f"{base_url}/wp-sitemap.xml", 
            f"{base_url}/post-sitemap.xml",
            f"{base_url}/recipe-sitemap.xml"
        ]
        
        for url in candidates:
            try:
                r = self.session.head(url, timeout=5)
                if r.status_code == 200: 
                    return url
            except: 
                pass
        
        return None
    
    def fetch_sitemap_urls(self, url: str, depth: int = 0) -> List[str]:
        if depth > 2: 
            return []
        
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code != 200: 
                return []
            
            # Use BeautifulSoup XML parser for robust parsing
            soup = BeautifulSoup(r.content, 'xml')
            all_urls = []

            # Handle Index Sitemaps (nested)
            if soup.find('sitemap'):
                sub_maps = [loc.text for loc in soup.find_all('loc')]
                targets = [s for s in sub_maps if 'post' in s or 'recipe' in s]
                if not targets: 
                    targets = sub_maps
                
                for sub in targets[:3]: 
                    all_urls.extend(self.fetch_sitemap_urls(sub, depth + 1))
                return all_urls
            
            # Handle URL Sitemaps
            if soup.find('url'):
                 return [loc.text for loc in soup.find_all('loc')]
            
            return []

        except Exception as e:
            logger.warning(f"Sitemap parse error {url}: {e}")
            return []
    
    def get_urls_for_site(self, site_url: str, force_refresh: bool = False) -> List[RecipeCandidate]:
        if not force_refresh:
            cached = self.storage.get_cached_sitemap(site_url)
            if cached:
                return [RecipeCandidate(url=u) for u in cached['urls']]
        
        sitemap_url = self.find_sitemap(site_url)
        if not sitemap_url: 
            return []
        
        urls = self.fetch_sitemap_urls(sitemap_url)
        self.storage.cache_sitemap(site_url, sitemap_url, urls)
        return [RecipeCandidate(url=u) for u in urls]

# ============================================================================
# RECIPE VERIFIER
# ============================================================================

class RecipeVerifier:
    def __init__(self, session: requests.Session):
        self.session = session
    
    def is_paranoid_skip(self, url: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
        try:
            path = urlparse(url).path
            slug = path.strip("/").split("/")[-1].lower()
            
            if LISTICLE_REGEX.search(slug): 
                return f"Listicle detected: {slug}"
            
            for kw in BAD_KEYWORDS:
                if kw in slug: 
                    return f"Bad keyword: {kw}"
            
            if soup:
                title = soup.title.string.lower() if soup.title else ""
                if "best recipes" in title or "top 10" in title: 
                    return "Listicle title"
        
        except: 
            pass
        
        return None
    
    def verify_recipe(self, url: str) -> Tuple[bool, Optional[BeautifulSoup], Optional[str]]:
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code != 200: 
                return False, None, f"HTTP {r.status_code}"
            
            # Recipe detection
            is_recipe = False
            soup = None
            
            if '"@type":"Recipe"' in r.text or '"@type": "Recipe"' in r.text:
                is_recipe = True
            
            if not is_recipe:
                soup = BeautifulSoup(r.content, 'lxml')
                if soup.find(class_=lambda x: x and any(cls in x for cls in ['wp-recipe-maker', 'tasty-recipes', 'mv-create-card', 'recipe-card'])):
                    is_recipe = True
            
            if not is_recipe: 
                return False, soup, "No recipe detected"
            
            if soup is None: 
                soup = BeautifulSoup(r.content, 'lxml')
            
            # Paranoid checks
            skip_reason = self.is_paranoid_skip(url, soup)
            if skip_reason: 
                return False, soup, skip_reason
            
            return True, soup, None
        
        except Exception as e:
            return False, None, f"Exception: {str(e)}"

# ============================================================================
# IMPORT MANAGER
# ============================================================================

class ImportManager:
    def __init__(self, session: requests.Session, storage: StorageManager, rate_limiter: RateLimiter, dry_run: bool):
        self.session = session
        self.storage = storage
        self.rate_limiter = rate_limiter
        self.dry_run = dry_run
    
    def import_to_mealie(self, url: str) -> Tuple[bool, Optional[str]]:
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would import to Mealie: {url}")
            return True, None
        
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        try:
            self.rate_limiter.wait_if_needed(MEALIE_URL)
            r = self.session.post(
                f"{MEALIE_URL}/api/recipes/create-url", 
                headers=headers, 
                json={"url": url}, 
                timeout=20
            )
            
            if r.status_code == 201:
                logger.info(f"   ✅ [Mealie] Imported: {url}")
                return True, None
            elif r.status_code == 409:
                logger.info(f"   ⚠️ [Mealie] Duplicate: {url}")
                return True, None
            else:
                return False, f"HTTP {r.status_code}"
        
        except Exception as e:
            return False, str(e)

    def import_to_tandoor(self, url: str) -> Tuple[bool, Optional[str]]:
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would import to Tandoor: {url}")
            return True, None
        
        headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
        try:
            self.rate_limiter.wait_if_needed(TANDOOR_URL)
            r = self.session.post(
                f"{TANDOOR_URL}/api/recipe/import-url/", 
                headers=headers, 
                json={"url": url}, 
                timeout=20
            )
            
            if r.status_code in [200, 201]:
                logger.info(f"   ✅ [Tandoor] Imported: {url}")
                return True, None
            else:
                return False, f"HTTP {r.status_code}"
        
        except Exception as e:
            return False, str(e)
    
    def import_recipe(self, url: str) -> bool:
        success = False
        
        if MEALIE_ENABLED:
            m_ok, _ = self.import_to_mealie(url)
            success = success or m_ok
        
        if TANDOOR_ENABLED:
            t_ok, _ = self.import_to_tandoor(url)
            success = success or t_ok
            
        return success

# ============================================================================
# CLI & MAIN
# ============================================================================

def validate_config():
    """Check for common misconfigurations."""
    issues = []
    
    if not MEALIE_ENABLED and not TANDOOR_ENABLED and not DRY_RUN:
        issues.append("⚠️  Warning: Both Mealie and Tandoor are disabled. Nothing will be imported!")
    
    if MEALIE_ENABLED and MEALIE_API_TOKEN == 'your-token':
        issues.append("⚠️  Warning: MEALIE_API_TOKEN not configured (still set to default)")
        
    if TANDOOR_ENABLED and TANDOOR_API_KEY == 'your-key':
        issues.append("⚠️  Warning: TANDOOR_API_KEY not configured (still set to default)")
        
    for issue in issues:
        logger.warning(issue)

def print_summary(storage: StorageManager):
    logger.info("=" * 50)
    logger.info("📊 Session Summary:")
    logger.info(f"   Total Imported: {len(storage.imported)}")
    logger.info(f"   Total Rejected: {len(storage.rejects)}")
    logger.info(f"   In Retry Queue: {len(storage.retry_queue)}")
    logger.info(f"   Cached Sitemaps: {len(storage.sitemap_cache)}")
    logger.info("=" * 50)

def load_sites_from_source(source_path: str = None) -> List[str]:
    """Load sites from various sources with priority: CLI > local file > env > defaults"""
    
    def parse_sites_json(data) -> List[str]:
        """Parse sites from JSON, handling both array and object formats."""
        if isinstance(data, list):
            # Simple array format: ["url1", "url2", ...]
            return [s for s in data if isinstance(s, str) and s.startswith('http')]
        elif isinstance(data, dict) and 'sites' in data:
            # Object format: {"sites": ["url1", "url2", ...]}
            sites = data['sites']
            return [s for s in sites if isinstance(s, str) and s.startswith('http')]
        else:
            logger.error("Invalid sites.json format. Expected array or object with 'sites' key.")
            return []
    
    # 1. CLI Argument
    if source_path:
        if os.path.exists(source_path):
            try:
                with open(source_path, 'r') as f: 
                    data = json.load(f)
                    return parse_sites_json(data)
            except Exception as e: 
                logger.error(f"Failed to load CLI sites file: {e}")
                sys.exit(1)
        else:
            logger.error(f"File not found: {source_path}")
            sys.exit(1)

    # 2. Local sites.json
    if os.path.exists('sites.json'):
        try:
            with open('sites.json', 'r') as f: 
                data = json.load(f)
                return parse_sites_json(data)
        except Exception as e:
            logger.warning(f"Failed to load sites.json: {e}")
            pass

    # 3. Environment variable
    if os.getenv('SITES'):
        return [s.strip() for s in os.getenv('SITES').split(',') if s.strip()]

    # 4. Defaults (The Full Curated List)
    return DEFAULT_SITES

def main():
    parser = argparse.ArgumentParser(description="Recipe Dredger: Intelligent Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scan without importing")
    parser.add_argument("--limit", type=int, default=DEFAULT_TARGET, help="Recipes to import per site")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="URLs to scan per site")
    parser.add_argument("--sites", type=str, help="Path to JSON file containing site URLs")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh crawl (ignore sitemap cache)")
    parser.add_argument("--version", action="version", version=f"Recipe Dredger {VERSION}")
    args = parser.parse_args()

    # Configuration Override
    DRY_RUN_MODE = args.dry_run or DRY_RUN
    TARGET_COUNT = args.limit
    SCAN_DEPTH_COUNT = args.depth
    FORCE_REFRESH = args.no_cache
    
    validate_config()
    
    sites_list = load_sites_from_source(args.sites)

    logger.info(f"🍲 Recipe Dredger Started ({VERSION})")
    logger.info(f"   Mode: {'DRY RUN' if DRY_RUN_MODE else 'LIVE IMPORT'}")
    logger.info(f"   Targets: {len(sites_list)} sites")
    logger.info(f"   Limit: {TARGET_COUNT} per site")
    
    # Initialize components
    storage = StorageManager()
    killer = GracefulKiller()
    session = get_session()
    rate_limiter = RateLimiter()
    crawler = SitemapCrawler(session, storage)
    verifier = RecipeVerifier(session)
    importer = ImportManager(session, storage, rate_limiter, DRY_RUN_MODE)
    
    # Process sites
    random.shuffle(sites_list)
    
    # Visual Progress Bar (optional tqdm)
    iterator = sites_list
    if TQDM_AVAILABLE and len(sites_list) > 1:
        iterator = tqdm(sites_list, desc="Processing Sites", unit="site")

    for site in iterator:
        # Check for graceful shutdown
        if killer.kill_now: 
            break
        
        if not TQDM_AVAILABLE: 
            logger.info(f"🌍 Processing Site: {site}")
        
        site_stats = {'imported': 0, 'rejected': 0, 'errors': 0}
        
        raw_candidates = crawler.get_urls_for_site(site, force_refresh=FORCE_REFRESH)
        if not raw_candidates: 
            continue
        
        candidates = raw_candidates[:SCAN_DEPTH_COUNT]
        random.shuffle(candidates)
        
        imported_count = 0
        for candidate in candidates:
            # Check for graceful shutdown in inner loop
            if killer.kill_now: 
                break
            
            if imported_count >= TARGET_COUNT: 
                break
            
            url = candidate.url
            
            if url in storage.imported or url in storage.rejects: 
                continue
            
            rate_limiter.wait_if_needed(url)
            
            is_recipe, soup, error = verifier.verify_recipe(url)
            
            if is_recipe:
                if importer.import_recipe(url):
                    storage.add_imported(url)
                    imported_count += 1
                    site_stats['imported'] += 1
                else:
                    site_stats['errors'] += 1
                    if not TQDM_AVAILABLE: 
                        logger.error(f"   ❌ Import failed: {url}")
            else:
                if not TQDM_AVAILABLE: 
                    logger.debug(f"   Skipping ({error}): {url}")
                storage.add_reject(url)
                site_stats['rejected'] += 1
        
        if not TQDM_AVAILABLE:
            logger.info(f"   Site Results: {site_stats['imported']} imported, "
                        f"{site_stats['rejected']} rejected, {site_stats['errors']} errors")
        
        storage.flush_all()
    
    # Print summary if not interrupted
    if not killer.kill_now:
        print_summary(storage)
    else:
        logger.info("⏸️  Gracefully stopped by signal")
        
    logger.info("🏁 Dredge Cycle Complete")

if __name__ == "__main__":
    main()
