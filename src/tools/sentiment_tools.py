from duckduckgo_search import DDGS

def get_news_sentiment(keywords=["Federal Reserve", "interest rates", "inflation", "geopolitics", "oil", "tech sector"]):
    try:
        ddgs = DDGS()
        results = []
        for kw in keywords:
            for r in ddgs.news(kw, max_results=2):
                results.append(f"[{r.get('source')}] {r.get('title')}: {r.get('body')}")
        
        if not results:
            return "No recent news headlines found."
            
        return "\n".join(results)
    except Exception as e:
        return "Headline sentiment: Neutral (News API temporarily unavailable)."
