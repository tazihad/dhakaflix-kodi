import sys
import re
import requests
import xbmc
import xbmcgui
import xbmcplugin
import os
import json
from urllib.parse import parse_qsl, quote, unquote, urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
MAX_THREADS = 20

# --- SEARCH CONFIGURATION (Updated to match Categories) ---
SEARCH_SERVERS = {
    'movies': [
        {'url': 'http://172.16.50.14', 'name': 'DHAKA-FLIX-14'},
        {'url': 'http://172.16.50.7',  'name': 'DHAKA-FLIX-7'}
    ],
    'series': [
        {'url': 'http://172.16.50.12', 'name': 'DHAKA-FLIX-12'},
        {'url': 'http://172.16.50.14', 'name': 'DHAKA-FLIX-14'},
        {'url': 'http://172.16.50.9',  'name': 'DHAKA-FLIX-9'}
    ]
}

# --- BROWSE CATEGORIES ---
MOVIE_CATEGORIES = [
    ('English Movies - 720p', 'http://172.16.50.7/DHAKA-FLIX-7/English%20Movies/'),
    ('English Movies - 1080p', 'http://172.16.50.14/DHAKA-FLIX-14/English%20Movies%20%281080p%29/'),
    ('Hindi Movies', 'http://172.16.50.14/DHAKA-FLIX-14/Hindi%20Movies/'),
    ('South Indian Movies', 'http://172.16.50.14/DHAKA-FLIX-14/SOUTH%20INDIAN%20MOVIES/South%20Movies/'),
    ('South Indian Hindi Dubbed', 'http://172.16.50.14/DHAKA-FLIX-14/SOUTH%20INDIAN%20MOVIES/Hindi%20Dubbed/'),
    ('West Bengal Bangla Movies', 'http://172.16.50.7/DHAKA-FLIX-7/Kolkata%20Bangla%20Movies/'),
    ('Animation Movies', 'http://172.16.50.14/DHAKA-FLIX-14/Animation%20Movies/'),
    ('Animation Movies - 1080p', 'http://172.16.50.14/DHAKA-FLIX-14/Animation%20Movies%20%281080p%29/'),
    ('Foreign Language Movies', 'http://172.16.50.7/DHAKA-FLIX-7/Foreign%20Language%20Movies/'),
    ('IMDB Top-250 Movies', 'http://172.16.50.14/DHAKA-FLIX-14/IMDb%20Top-250%20Movies/')
]

SERIES_CATEGORIES = [
    ('TV & Web Series', 'http://172.16.50.12/DHAKA-FLIX-12/TV-WEB-Series/'),
    ('Korean TV & Web Series', 'http://172.16.50.14/DHAKA-FLIX-14/KOREAN%20TV%20%26%20WEB%20Series/'),
    ('Anime & Cartoon Series', 'http://172.16.50.9/DHAKA-FLIX-9/Anime%20%26%20Cartoon%20TV%20Series/'),
    ('Documentary', 'http://172.16.50.9/DHAKA-FLIX-9/Documentary/'),
    ('WWE & AEW Wrestling', 'http://172.16.50.9/DHAKA-FLIX-9/WWE%20%26%20AEW%20Wrestling/'),
    ('Award & TV Shows', 'http://172.16.50.9/DHAKA-FLIX-9/Awards%20%26%20TV%20Shows/')
]

# --- HELPER FUNCTIONS ---

def clean_title(filename):
    name = unquote(filename)
    name = re.sub(r'\.(mkv|mp4|avi|flv|m4v)$', '', name, flags=re.IGNORECASE)
    name = name.replace('.', ' ').replace('_', ' ').strip()
    return name

def extract_meta(filename):
    name = clean_title(filename)
    match = re.search(r'\b(19\d{2}|20\d{2})\b', name)
    year = int(match.group(1)) if match else None
    
    if year:
        parts = name.split(str(year))
        title = parts[0].strip(' ()[]-')
    else:
        title = name
    return title, year

def extract_quality(filename):
    fn = filename.lower()
    quality = 'HD'
    if '2160p' in fn or '4k' in fn: quality = '4K'
    elif '1080p' in fn: quality = '1080p'
    elif '720p' in fn: quality = '720p'
    elif '480p' in fn: quality = '480p'
    
    source = ''
    if 'imax' in fn: source = 'IMAX'
    elif 'hmax' in fn: source = 'HMAX'
    elif 'bluray' in fn or 'blu-ray' in fn: source = 'BluRay'
    elif 'web-dl' in fn or 'webdl' in fn: source = 'WEB-DL'
    elif 'webrip' in fn: source = 'WEBRip'
    elif 'hdrip' in fn: source = 'HDRip'
    elif 'dvdrip' in fn: source = 'DVDRip'
    
    return f"{quality} {source}".strip()

# --- NETWORK / SCRAPING (BROWSE MODE) ---

def get_html(url):
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200: return r.text
    except: pass
    return None

def parse_html_for_image(url):
    html = get_html(url)
    if not html: return None
    match = re.search(r'href=["\']([^"\']+\.(?:jpg|png|jpeg))["\']', html, re.IGNORECASE)
    return urljoin(url, match.group(1)) if match else None

def fetch_links(url):
    html = get_html(url)
    if not html: return []
    raw_links = re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE)
    items = []
    for href in raw_links:
        if href.startswith(('?', '#')) or href in ['/', '../', './', 'Parent Directory']: continue
        if 'sort_by' in href: continue
        
        decoded = unquote(href)
        if decoded.endswith('/'): decoded = decoded[:-1]
        label = decoded.split('/')[-1]
        
        if label.lower() in ['_h5ai', 'h5ai', 'h51i', 'parent directory'] or '_h5ai' in href: continue
        if not label: continue

        full_url = urljoin(url, href)
        is_folder = href.endswith('/')
        ext = full_url.split('.')[-1].lower()
        if ext in ['mkv', 'mp4']: is_folder = False
        
        items.append({'label': label, 'url': full_url, 'is_folder': is_folder})
    return items

# --- SEARCH LOGIC (MULTI-SERVER API) ---

def execute_single_search(query, server):
    """Hits one server"""
    search_url = f"{server['url']}/{server['name']}/"
    payload = {
        "action": "get",
        "search": {
            "href": f"/{server['name']}/",
            "pattern": query,
            "ignorecase": True
        }
    }
    
    try:
        r = requests.post(search_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if 'search' in data:
                return [
                    {
                        'href': item['href'],
                        'fullUrl': server['url'] + item['href'],
                        'label': unquote(item['href'].split('/')[-1]),
                        'size': item.get('size')
                    }
                    for item in data['search']
                    if item.get('size') is not None and item['href'].lower().endswith(('.mkv', '.mp4'))
                ]
    except:
        pass
    return []

def get_smart_search_terms(query):
    cleaned = re.sub(r'[:\-–—]', ' ', query)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    words = [w for w in cleaned.split(' ') if len(w) > 2]
    
    terms = []
    # 1. Full Title (Exact)
    terms.append(cleaned)
    # 2. First 2 words
    if len(words) > 1: terms.append(" ".join(words[:2]))
    # 3. First word (only if title was long)
    if len(words) > 2: terms.append(words[0])
        
    return list(dict.fromkeys(terms))

def search_runner(type_key, query):
    servers = SEARCH_SERVERS.get(type_key, [])
    terms = get_smart_search_terms(query)
    all_results = []
    
    # Try most specific term first
    for term in terms:
        term_results = []
        
        # Parallel search across all configured servers
        with ThreadPoolExecutor(max_workers=len(servers)) as executor:
            futures = [executor.submit(execute_single_search, term, srv) for srv in servers]
            for future in as_completed(futures):
                res = future.result()
                if res: term_results.extend(res)
        
        if term_results:
            all_results = term_results
            break # Stop if we found matches with specific term
            
    return all_results

def search_input(type_key):
    kb = xbmc.Keyboard('', f'Search {type_key.title()}')
    kb.doModal()
    if kb.isConfirmed() and kb.getText():
        display_search_results(type_key, kb.getText())

def display_search_results(type_key, query):
    pDialog = xbmcgui.DialogProgress()
    pDialog.create('DhakaFlix', f'Searching {type_key}...')
    
    results = search_runner(type_key, query)
    
    if not results:
        pDialog.close()
        li = xbmcgui.ListItem("No results found")
        xbmcplugin.addDirectoryItem(HANDLE, "", li, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # Deduplicate results based on URL
    seen = set()
    unique_results = []
    for r in results:
        if r['fullUrl'] not in seen:
            unique_results.append(r)
            seen.add(r['fullUrl'])
            
    pDialog.update(100, "Processing results...")
    
    for item in unique_results:
        title, year = extract_meta(item['label'])
        quality = extract_quality(item['label'])
        
        display_title = f"{title}"
        if year: display_title += f" ({year})"
        display_title += f" - [COLOR yellow]{quality}[/COLOR]"
        
        li = xbmcgui.ListItem(display_title)
        video_info = {'title': title, 'mediatype': 'video'}
        if year: video_info['year'] = year
        
        li.setInfo('video', video_info)
        li.setArt({'icon': 'DefaultVideo.png'})
        li.setProperty('IsPlayable', 'true')
        
        url = build_url(f"mode=play&url={quote(item['fullUrl'])}")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)
        
    pDialog.close()
    xbmcplugin.endOfDirectory(HANDLE)

# --- KODI MENUS ---

def build_url(query):
    return BASE_URL + '?' + query

def main_menu():
    import xbmcaddon
    addon = xbmcaddon.Addon()
    icon = addon.getAddonInfo('icon')
    fanart = addon.getAddonInfo('fanart')
    
    items = [
        ("Movies", "movies_root"),
        ("TV Series", "series_root"),
        ("Search Movies", "search_input&type=movies"),
        ("Search TV Series", "search_input&type=series")
    ]

    for name, mode in items:
        li = xbmcgui.ListItem(name)
        li.setArt({'icon': icon, 'thumb': icon, 'fanart': fanart})
        
        # If mode contains parameters (like search_input&type=), handle correctly
        if '&' in mode:
            # Split mode and params
            # e.g. search_input&type=movies
            url = build_url(f"mode={mode}")
        else:
            url = build_url(f"mode={mode}")
            
        # Search is a folder? No, Search opens input.
        # However, to make it clickable in Kodi menu structure, we usually make it a directory item
        # that calls the input function.
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    
    xbmcplugin.endOfDirectory(HANDLE)

def movies_menu():
    for title, link in MOVIE_CATEGORIES:
        li = xbmcgui.ListItem(title)
        url = build_url(f"mode=browse&url={quote(link)}")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)

def series_menu():
    for title, link in SERIES_CATEGORIES:
        li = xbmcgui.ListItem(title)
        url = build_url(f"mode=browse&url={quote(link)}")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)

def browse(url):
    pDialog = xbmcgui.DialogProgress()
    pDialog.create('DhakaFlix', 'Scraping directory...')
    is_wrestling = 'WWE%20%26%20AEW%20Wrestling' in url or 'WWE & AEW Wrestling' in unquote(url)

    items = fetch_links(url)
    if not items:
        pDialog.close()
        xbmcplugin.endOfDirectory(HANDLE)
        return

    items.sort(key=lambda x: (not x['is_folder'], x['label'].lower()))
    folders = [i for i in items if i['is_folder']]
    
    # Threaded Folder Image Scan
    folder_images = {}
    if folders:
        pDialog.update(10, 'Scanning folders...')
        def check_art(item):
            return (item['url'], parse_html_for_image(item['url']))

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futures = [ex.submit(check_art, f) for f in folders]
            for i, f in enumerate(as_completed(futures)):
                if pDialog.iscanceled(): break
                try:
                    u, img = f.result()
                    if img: folder_images[u] = img
                except: pass
                pDialog.update(int(10 + (i/len(folders)*80)))

    # Local Files Scan
    local_poster = None
    local_subs = []
    for item in items:
        if not item['is_folder']:
            if item['label'].lower().endswith(('.jpg', '.png', '.jpeg')):
                if not local_poster: local_poster = item['url']
            if item['url'].lower().endswith(('srt', 'ass', 'sub', 'smi', 'vtt')):
                local_subs.append(item['url'])

    for item in items:
        if pDialog.iscanceled(): break
        ext = item['url'].split('.')[-1].lower()
        
        if item['is_folder']:
            li = xbmcgui.ListItem(item['label'])
            li.setInfo('video', {'title': item['label'], 'mediatype': 'video'})
            art = folder_images.get(item['url'])
            if art: li.setArt({'poster': art, 'thumb': art, 'fanart': art})
            else: li.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(HANDLE, build_url(f"mode=browse&url={quote(item['url'])}"), li, isFolder=True)
            
        elif ext in ['mkv', 'mp4']:
            if is_wrestling:
                title, year = unquote(item['label']), None
            else:
                title, year = extract_meta(item['label'])
            
            li = xbmcgui.ListItem(title)
            info = {'title': title, 'mediatype': 'video'}
            if year: info['year'] = year
            li.setInfo('video', info)
            
            if local_poster: li.setArt({'poster': local_poster, 'thumb': local_poster, 'fanart': local_poster})
            else: li.setArt({'icon': 'DefaultVideo.png'})
            
            # Subtitle matching
            base = os.path.splitext(item['label'])[0].lower()
            subs = []
            for s in local_subs:
                s_dec = unquote(s).lower()
                if base in s_dec or len(local_subs) == 1:
                    subs.append(s)
            if subs: li.setSubtitles(subs)
            
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.addDirectoryItem(HANDLE, build_url(f"mode=play&url={quote(item['url'])}"), li, isFolder=False)
            
    pDialog.close()
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)

def play_video(url):
    li = xbmcgui.ListItem(path=url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)

def router(paramstring):
    params = dict(parse_qsl(paramstring))
    mode = params.get('mode')
    
    if mode is None:
        main_menu()
    elif mode == 'movies_root':
        movies_menu()
    elif mode == 'series_root':
        series_menu()
    elif mode == 'browse':
        browse(params.get('url'))
    elif 'search_input' in str(mode):
        # Handle 'search_input' and 'search_input&type=x'
        type_key = params.get('type', 'movies')
        search_input(type_key)
    elif mode == 'play':
        play_video(params.get('url'))

if __name__ == '__main__':
    router(sys.argv[2][1:])