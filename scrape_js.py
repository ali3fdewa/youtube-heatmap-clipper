import urllib.request
import re

url = "https://klipers.pro/assets/index.CYiItRG_.js"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')
        
        strings = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content)
        
        changelog_keywords = ['changelog', 'v1.', 'v2.', 'fitur', 'update', 'baru', 'rilis', 'added', 'fixed', 'perbaikan', 'menambahkan']
        
        found = []
        for s in strings:
            if len(s) > 10 and len(s) < 300:
                s_lower = s.lower()
                if any(kw in s_lower for kw in changelog_keywords):
                    found.append(s)
                    
        with open("changelog_extracted.txt", "w", encoding="utf-8") as f:
            for s in list(dict.fromkeys(found)):
                f.write(f"- {s}\n")
        print("Done writing to changelog_extracted.txt")
except Exception as e:
    print("Error:", e)
