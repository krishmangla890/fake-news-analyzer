import sqlite3
import re
import os
from urllib.parse import urlparse
from newspaper import Article
# Naya aur sabse powerful scraper
from curl_cffi import requests as cffi_requests

class KrishSourceAndBiasAnalyzer:
    def __init__(self, db_name="source_credibility.db"):
        self.db_name = db_name
        self._init_db()
        
        self.emotional_lexicon = [
            "shocking", "outrageous", "catastrophic", "devastating", 
            "horrific", "unbelievable", "massive", "disaster", "crisis"
        ]
        self.loaded_lexicon = [
            "radical", "extremist", "corrupt", "scheme", 
            "propaganda", "agenda", "hypocrite", "failure", "attack"
        ]

    def _init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                domain TEXT PRIMARY KEY,
                reliability_score REAL,
                category TEXT
            )
        ''')
        comprehensive_sources = [
            ('reuters.com', 95.0, 'Mainstream News / Wire'),
            ('bbc.com', 90.0, 'Mainstream News'),
            ('apnews.com', 95.0, 'Mainstream News / Wire'),
            ('thehindu.com', 90.0, 'Mainstream News'),
            ('ndtv.com', 80.0, 'Mainstream News'),
            ('nytimes.com', 88.0, 'Mainstream News'),
            ('theonion.com', 30.0, 'Satire'),
            ('infowars.com', 15.0, 'Unreliable / Conspiracy'),
            ('naturalnews.com', 20.0, 'Pseudoscience / Unreliable'),
            ('thegatewaypundit.com', 25.0, 'Questionable / Fake News'),
            ('rt.com', 40.0, 'State-Affiliated Media')
        ]
        cursor.executemany('INSERT OR IGNORE INTO sources VALUES (?, ?, ?)', comprehensive_sources)
        conn.commit()
        conn.close()

    def _calculate_smart_heuristics(self, domain: str) -> tuple:
        score = 40.0 
        heuristics_applied = ["Unknown source (Base score 40)"]
        category = "Unverified / Unknown Source"
        domain_lower = domain.lower()

        if any(k in domain_lower for k in ['news', 'times', 'post', 'herald', 'daily', 'wire', 'express', 'chronicle']):
            score += 15.0
            category = "Likely Mainstream"
            heuristics_applied.append("Mainstream journalism keyword found (+15)")

        if any(k in domain_lower for k in ['truth', 'voice', 'patriot', 'alert', 'conspiracy', 'real', 'liberty', 'awake', 'freedom']):
            score -= 15.0
            category = "Suspicious / Highly Partisan"
            heuristics_applied.append("Suspicious/Hyper-partisan keyword detected (-15)")

        if domain_lower.endswith('.edu') or domain_lower.endswith('.gov'):
            score += 30.0
            category = "Academic / Government Source"
            heuristics_applied.append("Trusted TLD (.edu / .gov) (+30)")
        elif domain_lower.endswith('.org'):
            score += 10.0
            heuristics_applied.append("Non-profit TLD (.org) (+10)")
        elif domain_lower.endswith('.xyz') or domain_lower.endswith('.top') or domain_lower.endswith('.info') or domain_lower.endswith('.tv'):
            score -= 20.0
            category = "Suspicious TLD / Low Trust"
            heuristics_applied.append("Suspicious TLD extension penalty (-20)")

        if domain_lower.count('-') > 2:
            score -= 15.0
            heuristics_applied.append("Multiple hyphens (potential spam pattern) (-15)")

        score = max(10.0, min(score, 85.0))
        return score, category, heuristics_applied

    def get_source_score(self, domain: str) -> dict:
        domain = domain.lower().strip()
        if domain.startswith('www.'):
            domain = domain[4:]

        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT reliability_score, category FROM sources WHERE domain = ?', (domain,))
        result = cursor.fetchone()

        if result:
            conn.close()
            return {
                "domain": domain,
                "reliability_score": result[0],
                "source_type": "Curated Database",
                "category": result[1]
            }
        else:
            score, category, heuristics = self._calculate_smart_heuristics(domain)
            cursor.execute('INSERT OR REPLACE INTO sources (domain, reliability_score, category) VALUES (?, ?, ?)', 
                           (domain, score, category))
            conn.commit()
            conn.close()

            return {
                "domain": domain,
                "reliability_score": score,
                "source_type": "Auto-Cached & Saved to DB",
                "category": category,
                "heuristics_used": heuristics
            }

    def get_bias_analysis(self, text: str) -> dict:
        text_lower = text.lower()
        flagged_spans = []
        all_bias_words = self.emotional_lexicon + self.loaded_lexicon
        
        for word in all_bias_words:
            for match in re.finditer(r'\b' + re.escape(word) + r'\b', text_lower):
                start, end = match.span()
                category = "Emotional Appeal" if word in self.emotional_lexicon else "Loaded Language"
                flagged_spans.append({
                    "start": start,
                    "end": end,
                    "text": text[start:end],
                    "category": category
                })

        words_in_text = len(text.split())
        if words_in_text > 0:
            bias_ratio = len(flagged_spans) / words_in_text
            bias_score = min(round(bias_ratio * 300, 2), 100.0)
            subjectivity_score = min(round((len(flagged_spans) * 1.5) / words_in_text * 100, 2), 100.0)
        else:
            bias_score = 0.0
            subjectivity_score = 0.0

        return {
            "bias_score": bias_score,
            "subjectivity_score": subjectivity_score,
            "total_flagged_words": len(flagged_spans),
            "sample_highlighted_spans": flagged_spans
        }

    def analyze_url(self, url: str) -> dict:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # 1. Domain ka source score calculate karo
        source_result = self.get_source_score(domain)
        
        title = "Unknown"
        text = ""
        
        try:
            # 2. curl_cffi use karke exact Chrome Browser impersonate karo (Sabse powerful bypass)
            response = cffi_requests.get(url, impersonate="chrome110", timeout=15)
            
            if response.status_code == 200:
                article = Article(url)
                article.set_html(response.text)
                article.parse()
                title = article.title
                text = article.text
            else:
                raise Exception(f"Website rejected request with Status Code: {response.status_code}")
                
        except Exception as e:
            return {
                "article_title": "Blocked by High-Level Security",
                "source_credibility": source_result,
                "bias_analysis": {
                    "bias_score": 0.0,
                    "subjectivity_score": 0.0,
                    "total_flagged_words": 0,
                    "sample_highlighted_spans": [],
                    "note": f"Could not extract text: {str(e)}"
                }
            }

        if not text or len(text.strip()) < 30:
            return {
                "article_title": title,
                "source_credibility": source_result,
                "bias_analysis": {
                    "bias_score": 0.0,
                    "subjectivity_score": 0.0,
                    "total_flagged_words": 0,
                    "sample_highlighted_spans": [],
                    "note": "Extracted text is too short or empty."
                }
            }

        bias_result = self.get_bias_analysis(text)

        return {
            "article_title": title,
            "source_credibility": source_result,
            "bias_analysis": bias_result
        }

# --- Test ---
if __name__ == "__main__":
    import json
    
    # Purane cached score ko hatane ka code
    db_path = "source_credibility.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM sources WHERE domain = 'thepeoplesvoice.tv'")
            conn.commit()
            conn.close()
        except Exception:
            pass

    analyzer = KrishSourceAndBiasAnalyzer()
    
    print("Testing Ultra-Secure URL with curl_cffi:")
    result = analyzer.analyze_url("https://www.truthdig.com/articles/making-a-mess-of-climate-week/")
    
    print(json.dumps(result, indent=4))