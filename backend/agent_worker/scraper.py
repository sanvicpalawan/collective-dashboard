"""
Real lead discovery for the `lead_generation` job — no API keys, free sources.

Why not Google Maps / Yellow Pages:
- Google Maps has no free search API, its HTML is JS-only and terms-hostile, and
  Google blocks datacenter IPs within a few requests.
- Yellow Pages is US/Canada; the PH equivalent (yellowpages.com.ph) now redirects
  to an ad tracker, and it is not a business directory any more.

What actually returns real data:
  1. Nominatim POI search    — free-text business search over OpenStreetMap with
                               extratags (name, phone, website). Best coverage of
                               anything free. 1 request/second, requires a UA.
  2. Overpass tag search     — catches businesses that are tagged but not
                               name-searchable (e.g. amenity=dentist).
  3. DuckDuckGo HTML search  — best effort, to find a business's own website.
  4. Website enrichment      — read that website (and /contact) for `mailto:` /
                               `tel:` and the business name.

OpenStreetMap data © OpenStreetMap contributors, ODbL.

Politeness (a scraper that gets banned is worthless): identifies itself in the
User-Agent, 20-60s timeouts, a delay between requests, and hard caps — one
geocode, two OSM queries, two searches, eight page fetches per job.
"""
from __future__ import annotations

import re
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = "ffinn-leadgen/1.0 (lead research; +https://merqato.digital)"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"

GEO_TIMEOUT = 25
OVERPASS_TIMEOUT = 60
HTTP_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.1
MAX_PAGE_FETCHES = 8
MAX_CANDIDATES = 40

# Nominatim "class" values that are places, not businesses.
NON_BUSINESS_CLASSES = {
    "boundary", "place", "highway", "waterway", "railway", "natural", "landuse",
    "administrative", "route", "aeroway", "power",
}

# Domains that aggregate other businesses: never treat them as the business itself.
DIRECTORY_HOSTS = (
    "facebook.", "fb.com", "instagram.", "linkedin.", "twitter.", "x.com", "youtube.",
    "tiktok.", "pinterest.", "reddit.", "wikipedia.", "wikidata.", "google.", "g.co",
    "bing.", "duckduckgo.", "yelp.", "tripadvisor.", "foursquare.", "whatclinic.",
    "clinicbooking.", "clinicfinderph.", "doktor.ph", "yellowpages.", "mapcarta.",
    "booking.com", "agoda.", "expedia.", "airbnb.", "trip.com", "hotels.com", "trivago.",
    "indeed.", "jobstreet.", "olx.", "lazada.", "shopee.", "grabfood.", "foodpanda.",
    "thumbtack.", "angi.", "bbb.org", "glassdoor.", "crunchbase.", "trustpilot.",
    "sys-rsrv.com", "cloudbeds.", "site-minder.", "hotelscombined.",
)

# Addresses that are infrastructure, never a business contact.
EMAIL_BLOCKLIST_HOSTS = (
    "example.com", "example.org", "sentry.io", "wixpress.com", "domain.com",
    "email.com", "yourdomain.com", "cloudflare.com", "sentry.wixpress.com",
)
EMAIL_BLOCKLIST_LOCAL = ("noreply", "no-reply", "donotreply", "postmaster", "abuse", "webmaster")

GENERIC_TITLES = {
    "home", "welcome", "contact", "contact us", "about", "about us", "index",
    "untitled", "page not found", "404", "not found",
}

# Niche keywords → OpenStreetMap tags. First match on the niche string wins.
NICHE_TAGS: dict[str, list[tuple[str, str]]] = {
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "dental": [("amenity", "dentist"), ("healthcare", "dentist")],
    "orthodont": [("amenity", "dentist"), ("healthcare", "dentist")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic")],
    "doctor": [("amenity", "doctors"), ("healthcare", "doctor")],
    "physician": [("amenity", "doctors"), ("healthcare", "doctor")],
    "hospital": [("amenity", "hospital")],
    "pharmac": [("amenity", "pharmacy")],
    "resort": [("tourism", "resort"), ("tourism", "hotel"), ("tourism", "guest_house")],
    "hotel": [("tourism", "hotel"), ("tourism", "resort")],
    "guesthouse": [("tourism", "guest_house")],
    "hostel": [("tourism", "hostel")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee": [("amenity", "cafe")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "bakery": [("shop", "bakery")],
    "salon": [("shop", "beauty"), ("shop", "hairdresser")],
    "spa": [("leisure", "spa"), ("shop", "beauty")],
    "barber": [("shop", "hairdresser")],
    "gym": [("leisure", "fitness_centre")],
    "lawyer": [("office", "lawyer")],
    "attorney": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "architect": [("office", "architect")],
    "real estate": [("office", "estate_agent")],
    "travel": [("shop", "travel_agency")],
    "car rental": [("amenity", "car_rental")],
    "hardware": [("shop", "hardware")],
    "supermarket": [("shop", "supermarket")],
    "laundry": [("shop", "laundry")],
    "pet": [("shop", "pet")],
    "veterinar": [("amenity", "veterinary")],
}

PHONE_RE = re.compile(
    r"(?:\+63|0063|0)\s?\(?\d{1,3}\)?[\s.\-]?\d{3}[\s.\-]?\d{3,4}"
    r"|\(0\d{2,3}\)\s?\d{3}[\s.\-]?\d{4}"
)


@dataclass
class Candidate:
    business_name: str
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    locality: Optional[str] = None
    source: str = "osm"
    # True once we have actually read the business's own page.
    verified: bool = False


@dataclass
class SearchReport:
    leads: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def log(message: str, **fields) -> None:
    """Same shape as the worker's log lines so `docker compose logs` reads cleanly."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"{stamp} LEADS   {message}{(' ' + extra) if extra else ''}", flush=True)


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def _fetch(session: requests.Session, url: str, **kwargs) -> Optional[requests.Response]:
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT, **kwargs)
        if r.status_code >= 400:
            log("http error", url=url[:80], status=r.status_code)
            return None
        return r
    except requests.RequestException as exc:
        log("http failed", url=url[:80], error=type(exc).__name__)
        return None


# ── Small cleaners ───────────────────────────────────────────────────────────
def _clean_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"\s+", " ", name).strip(" -|–—•·")
    return name[:200]


def _clean_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.split(";")[0].strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")
    return url[:500]


def _clean_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    phone = urllib.parse.unquote(str(phone).split(";")[0]).replace("\xa0", " ").strip()
    if len(re.sub(r"\D", "", phone)) < 7:
        return None
    return re.sub(r"\s{2,}", " ", phone)[:40]


def _first_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return str(value).split(";")[0].strip() or None


# ── Source 1: Nominatim POI search (best free coverage) ──────────────────────
def nominatim_pois(
    session: requests.Session, niche: str, location: str, limit: int
) -> tuple[list[Candidate], list[str]]:
    """Free-text business search: "dentists, Palawan" → named POIs with extratags."""
    notes: list[str] = []
    params = {
        "q": f"{niche}, {location}",
        "format": "jsonv2",
        "limit": min(limit * 2, 40),
        "extratags": 1,
        "addressdetails": 1,
        "countrycodes": "ph",
    }
    r = _fetch(session, NOMINATIM_SEARCH_URL, params=params)
    if not r:
        notes.append("OpenStreetMap name search unavailable")
        return [], notes
    try:
        results = r.json()
    except ValueError:
        notes.append("OpenStreetMap name search returned invalid JSON")
        return [], notes

    found: list[Candidate] = []
    for item in results:
        if item.get("class") in NON_BUSINESS_CLASSES:
            continue
        name = _clean_name(item.get("name") or "")
        if len(name) < 3:
            continue
        extra = item.get("extratags") or {}
        address = item.get("address") or {}
        found.append(
            Candidate(
                business_name=name,
                website=_clean_url(extra.get("website") or extra.get("contact:website")),
                phone=_clean_phone(extra.get("phone") or extra.get("contact:phone")),
                locality=address.get("city") or address.get("town") or address.get("village"),
                source="osm",
            )
        )
    log("nominatim results", count=len(found))
    return found[:MAX_CANDIDATES], notes


# ── Source 2: Overpass tag search ────────────────────────────────────────────
def osm_tags_for(niche: str) -> list[tuple[str, str]]:
    n = niche.lower()
    for keyword, tags in NICHE_TAGS.items():
        if keyword in n:
            return tags
    return []


def overpass_pois(
    session: requests.Session, niche: str, location: str, limit: int
) -> tuple[list[Candidate], list[str]]:
    notes: list[str] = []
    tags = osm_tags_for(niche)
    if not tags:
        notes.append(f"no OpenStreetMap tag mapping for '{niche}'")
        return [], notes

    geo = _fetch(
        session,
        NOMINATIM_SEARCH_URL,
        params={"q": location, "format": "jsonv2", "limit": 1, "addressdetails": 0},
    )
    if not geo:
        notes.append(f"could not geocode '{location}'")
        return [], notes
    try:
        geo_json = geo.json()
    except ValueError:
        geo_json = []
    if not geo_json:
        notes.append(f"could not geocode '{location}'")
        return [], notes

    # Nominatim boundingbox order: [south, north, west, east]
    south, north, west, east = geo_json[0]["boundingbox"]
    bbox = f"{south},{west},{north},{east}"
    parts = "\n  ".join(f'nwr["{k}"="{v}"]({bbox});' for k, v in tags)
    query = f"[out:json][timeout:60];\n(\n  {parts}\n);\nout center tags {limit * 3};"

    try:
        r = session.post(OVERPASS_URL, data={"data": query}, timeout=OVERPASS_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as exc:
        log("overpass failed", error=type(exc).__name__)
        notes.append(f"OpenStreetMap tag query failed ({type(exc).__name__})")
        return [], notes

    local = (geo_json[0].get("display_name") or "").split(",")[0]
    found: list[Candidate] = []
    for el in payload.get("elements", []):
        t = el.get("tags") or {}
        name = _clean_name(t.get("name") or t.get("operator") or "")
        if len(name) < 3:
            continue
        found.append(
            Candidate(
                business_name=name,
                website=_clean_url(_first_value(t.get("website") or t.get("contact:website") or t.get("url"))),
                phone=_clean_phone(_first_value(t.get("phone") or t.get("contact:phone") or t.get("contact:mobile"))),
                locality=t.get("addr:city") or t.get("addr:town") or local or None,
                source="osm",
            )
        )
    log("overpass results", count=len(found))
    return found[:MAX_CANDIDATES], notes


# ── Source 3: DuckDuckGo HTML (best effort) ──────────────────────────────────
def _real_url(href: str) -> str:
    """DDG wraps every result: //duckduckgo.com/l/?uddg=<url>&rut=…"""
    if not href:
        return ""
    href = href.strip()
    parsed = urllib.parse.urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        return urllib.parse.unquote(urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0])
    if href.startswith("//"):
        return "https:" + href
    return href


def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _is_directory(url: str) -> bool:
    host = _host_of(url)
    return any(d in host for d in DIRECTORY_HOSTS)


def search_web(
    session: requests.Session, niche: str, location: str
) -> tuple[list[tuple[str, str]], list[str]]:
    """Business websites for the niche/location. Returns [(url, title)]."""
    notes: list[str] = []
    query = f"{niche} {location} contact"
    out: list[tuple[str, str]] = []
    seen_hosts: set[str] = set()

    for attempt in (1, 2):
        r = _fetch(session, DDG_HTML_URL, params={"q": query})
        if not r:
            break
        text = r.text
        blocked = "anomaly" in text.lower() or "unusual traffic" in text.lower()
        soup = BeautifulSoup(text, "html.parser")
        hits = soup.select("a.result__a")
        if blocked or not hits:
            log("ddg blocked", attempt=attempt, bytes=len(text))
            if attempt == 1:
                time.sleep(3.0)
                continue
            notes.append("web search unavailable (DuckDuckGo rate-limited this IP)")
            break

        for a in hits:
            url = _real_url(a.get("href") or "")
            if not url.startswith("http") or _is_directory(url):
                continue
            host = _host_of(url)
            if not host or host in seen_hosts:
                continue
            seen_hosts.add(host)
            out.append((url, a.get_text(" ", strip=True)))
            if len(out) >= 8:
                break
        log("web search", results=len(out))
        break

    return out, notes


# ── Website enrichment ───────────────────────────────────────────────────────
def _valid_email(addr: str) -> bool:
    local, _, host = addr.partition("@")
    if not local or not host or "." not in host or len(addr) > 254:
        return False
    if any(bad in host.lower() for bad in EMAIL_BLOCKLIST_HOSTS):
        return False
    if any(local.lower().startswith(bad) for bad in EMAIL_BLOCKLIST_LOCAL):
        return False
    if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)$", host, re.I):
        return False
    return True


def _email_matches_host(addr: str, host: str) -> bool:
    """A page's own mailto: — so a directory's support@ address never becomes a lead."""
    domain = addr.partition("@")[2].lower()
    return domain == host or domain.endswith("." + host) or host.endswith("." + domain)


def _name_from_slug(url: str) -> Optional[str]:
    """Last meaningful URL segment → a readable name ("identist-palawan-dental-clinic")."""
    segments = [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]
    for seg in reversed(segments):
        seg = re.sub(r"\.(html?|php|aspx?)$", "", seg, flags=re.I)
        words = [w for w in re.split(r"[-_]", seg) if w and not w.isdigit()]
        if len(words) >= 2 and sum(len(w) for w in words) >= 8:
            return " ".join(w.capitalize() for w in words)
    return None


def _looks_like_article(title: str) -> bool:
    """\"Expert Dental Care in Puerto Princesa, Palawan\" is a headline, not a name."""
    t = title.strip()
    words = t.split()
    if len(t) > 70:
        return True
    if "," in t and len(words) >= 5:
        return True
    if re.search(r"\b(?:in|at)\s+[A-Z]", t) and len(words) >= 5:
        return True
    return False


def _best_name(soup: BeautifulSoup, url: str) -> Optional[str]:
    """
    The business name, best source first.

    Business sites put their own name in <title> (\"iDentist Palawan Dental Clinic
    — Professional Dental Care\"); directories put an article headline in the <h1>
    and the business name in the URL slug.
    """
    options: list[str] = []
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        options.append(str(og["content"]))
    if soup.title:
        parts = [p for p in re.split(r"[|\u2013\u2014\u2022\u00b7]| - ", soup.title.get_text(strip=True)) if p.strip()]
        if parts:
            options.append(parts[0])
    h1 = soup.find("h1")
    if h1:
        options.append(h1.get_text(" ", strip=True))
    slug = _name_from_slug(url)
    if slug:
        options.append(slug)

    for raw in options:
        name = _clean_name(raw)
        if len(name) < 3 or name.lower() in GENERIC_TITLES:
            continue
        if _looks_like_article(name):
            continue
        return name
    return None


def parse_business_page(url: str, html_text: str) -> Optional[Candidate]:
    soup = BeautifulSoup(html_text, "html.parser")
    host = _host_of(url)

    name = _best_name(soup, url)
    if not name:
        return None

    emails: list[str] = []
    phones: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        low = href.lower()
        if low.startswith("mailto:"):
            addr = urllib.parse.unquote(href[7:].split("?")[0]).strip().lower()
            if _valid_email(addr) and _email_matches_host(addr, host) and addr not in emails:
                emails.append(addr)
        elif low.startswith("tel:"):
            got = _clean_phone(href[4:])
            if got and got not in phones:
                phones.append(got)

    if not phones:
        text = soup.get_text(" ", strip=True)[:6000]
        for match in PHONE_RE.findall(text):
            got = _clean_phone(match)
            if got and got not in phones:
                phones.append(got)
            if len(phones) >= 2:
                break

    return Candidate(
        business_name=name,
        website=url,
        email=emails[0] if emails else None,
        phone=phones[0] if phones else None,
        source="web",
    )


def enrich_from_website(session: requests.Session, candidate: Candidate) -> Candidate:
    """Read the business's own page (and /contact if needed) for email + phone."""
    if not candidate.website:
        return candidate

    r = _fetch(session, candidate.website)
    if not r:
        return candidate

    parsed = parse_business_page(candidate.website, r.text)
    if parsed:
        candidate = replace(
            candidate,
            email=candidate.email or parsed.email,
            phone=candidate.phone or parsed.phone,
            verified=True,
        )
        if candidate.source == "web":
            candidate = replace(candidate, business_name=parsed.business_name)

    if candidate.email:
        return candidate

    base = urllib.parse.urlsplit(candidate.website)
    for path in ("/contact", "/contact-us"):
        time.sleep(REQUEST_DELAY_SECONDS)
        contact_url = urllib.parse.urlunsplit((base.scheme, base.netloc, path, "", ""))
        rc = _fetch(session, contact_url)
        if not rc:
            continue
        parsed = parse_business_page(contact_url, rc.text)
        if parsed and parsed.email:
            candidate = replace(candidate, email=parsed.email, phone=candidate.phone or parsed.phone)
            break

    return candidate


# ── Orchestration ────────────────────────────────────────────────────────────
def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _merge(results: Iterable[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for c in results:
        key = _name_key(c.business_name)
        if not key:
            continue
        if key not in merged:
            merged[key] = c
            continue
        existing = merged[key]
        merged[key] = replace(
            existing,
            email=existing.email or c.email,
            phone=existing.phone or c.phone,
            website=existing.website or c.website,
            locality=existing.locality or c.locality,
        )
    return list(merged.values())


def find_leads(niche: str, location: str, limit: int = 10) -> SearchReport:
    """
    Real businesses for `niche` in `location`.

    Nominatim answers "which businesses are called/known as X here", Overpass
    answers "which businesses are tagged X here", DuckDuckGo finds their
    websites, and each website is read for an email. Results are ranked by how
    complete the contact record is — a name with a website outranks a bare name.
    """
    session = _session()
    report = SearchReport()

    named, notes_a = nominatim_pois(session, niche, location, limit)
    report.notes.extend(notes_a)

    time.sleep(REQUEST_DELAY_SECONDS)
    tagged, notes_b = overpass_pois(session, niche, location, limit)
    report.notes.extend(notes_b)

    time.sleep(REQUEST_DELAY_SECONDS)
    web_pairs, notes_c = search_web(session, niche, location)
    report.notes.extend(notes_c)

    web = [
        Candidate(business_name=_clean_name(_host_of(url).split(".")[0].replace("-", " ").title()),
                  website=url, source="web")
        for url, _title in web_pairs
    ]

    candidates = _merge(named + tagged + web)

    fetches = 0
    for idx, c in enumerate(candidates):
        if not c.website or c.email or fetches >= MAX_PAGE_FETCHES:
            continue
        time.sleep(REQUEST_DELAY_SECONDS)
        candidates[idx] = enrich_from_website(session, c)
        fetches += 1

    # A website that would not load (dead host, bad TLS) and told us nothing is not
    # a lead: the only thing we ever knew about it was its domain name.
    def _substantive(c: Candidate) -> bool:
        return c.source == "osm" or c.verified

    candidates = [
        c for c in candidates
        if len(_name_key(c.business_name)) >= 3 and _substantive(c)
    ]
    candidates.sort(
        key=lambda c: (
            c.email is None,
            c.phone is None,
            c.website is None,
            c.source != "osm",
        )
    )
    report.leads = candidates[:limit]

    log(
        "search done",
        niche=niche,
        location=location,
        nominatim=len(named),
        overpass=len(tagged),
        web=len(web_pairs),
        kept=len(report.leads),
        fetched=fetches,
    )
    return report
