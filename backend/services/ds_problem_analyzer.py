"""
Data Science Problem Analyzer — Powered by Pandas, NumPy & Scikit-learn.

Performs quantitative and qualitative analysis on scraped issues from
Reddit, HackerNews, StackOverflow, Dev.to, and GitHub:
- Pain Intensity Index calculation (lexical frustration + urgency scoring)
- Engagement & Virality weighting (upvotes, comments, ratio)
- TF-IDF Problem Clustering & Topic Extraction via Scikit-Learn
- Viability & Feasibility scoring
- DataFrame-based aggregation, retention, and CSV/JSON reporting
"""
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans

logger = logging.getLogger(__name__)

# Lexical dictionaries for pain and urgency analysis
FRUSTRATION_KEYWORDS = {
    "hate": 2.5, "awful": 2.2, "terrible": 2.2, "broken": 2.0, "impossible": 2.0,
    "frustrating": 2.0, "frustrated": 2.0, "nightmare": 2.4, "horrible": 2.2,
    "waste of time": 2.5, "annoying": 1.8, "pain": 1.7, "painful": 1.9,
    "sucks": 2.0, "struggling": 1.8, "struggle": 1.7, "fail": 1.5, "failed": 1.5,
    "bug": 1.3, "bugs": 1.4, "crash": 1.8, "crashes": 1.9, "slow": 1.4,
    "expensive": 1.6, "overpriced": 1.9, "complex": 1.3, "confusing": 1.5,
    "missing": 1.4, "lack": 1.4, "unreliable": 2.0, "tedious": 1.7,
}

URGENCY_KEYWORDS = {
    "need": 1.5, "urgent": 2.5, "asap": 2.5, "help": 1.6, "critical": 2.2,
    "immediately": 2.3, "looking for": 1.8, "anyone know": 1.5, "alternative to": 2.0,
    "recommend": 1.4, "recommendation": 1.4, "wish there was": 2.4, "why is there no": 2.5,
    "how to solve": 1.7, "workaround": 1.8, "tired of": 2.2, "please": 1.2
}

TECH_KEYWORDS = {
    "api": 1.2, "database": 1.2, "python": 1.2, "ai": 1.5, "llm": 1.5,
    "automation": 1.6, "cli": 1.3, "dashboard": 1.4, "scraper": 1.3,
    "saas": 1.6, "workflow": 1.5, "integration": 1.4, "cloud": 1.2
}


class DataScienceProblemAnalyzer:
    """Quantitative Data Science engine for real-world problem extraction."""

    def __init__(self, items: List[Dict[str, Any]]):
        self.raw_items = items
        self.df = self._build_dataframe(items)

    def _build_dataframe(self, items: List[Dict[str, Any]]) -> pd.DataFrame:
        """Transform raw items into a structured Pandas DataFrame with clean fields."""
        if not items:
            return pd.DataFrame(columns=[
                "platform", "title", "content", "url", "author", "score",
                "comments", "subreddit", "text", "clean_text", "pain_score",
                "urgency_score", "engagement_score", "composite_priority"
            ])

        records = []
        for it in items:
            title = str(it.get("title", "") or "")
            content = str(it.get("content", "") or "")
            full_text = f"{title}. {content}".strip()
            score = float(it.get("score", 0) or 0)
            comments = float(it.get("num_comments", it.get("comments_count", 0)) or 0)

            records.append({
                "platform": it.get("platform", "unknown"),
                "title": title,
                "content": content,
                "url": it.get("url", ""),
                "author": it.get("author", "anonymous"),
                "score": max(0.0, score),
                "comments": max(0.0, comments),
                "subreddit": it.get("subreddit", ""),
                "tags": it.get("tags", []),
                "text": full_text,
                "created_at": it.get("created_utc", datetime.now(timezone.utc).timestamp()),
            })

        df = pd.DataFrame(records)
        df["clean_text"] = df["text"].apply(self._clean_text)
        return df

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.lower()
        text = re.sub(r"http\S+|www\S+|https\S+", "", text, flags=re.MULTILINE)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def compute_metrics(self) -> pd.DataFrame:
        """Compute statistical data science metrics for each issue candidate."""
        if self.df.empty:
            return self.df

        # 1. Pain Intensity Score
        def calc_pain(text: str) -> float:
            score = 0.0
            words = text.split()
            for w in words:
                if w in FRUSTRATION_KEYWORDS:
                    score += FRUSTRATION_KEYWORDS[w]
            # Normalization per length with a log scale
            return min(10.0, round(score * 2.0 / (np.log1p(len(words)) + 1.0), 2))

        # 2. Urgency Score
        def calc_urgency(text: str) -> float:
            score = 0.0
            words = text.split()
            for w in words:
                if w in URGENCY_KEYWORDS:
                    score += URGENCY_KEYWORDS[w]
            return min(10.0, round(score * 2.5 / (np.log1p(len(words)) + 1.0), 2))

        self.df["pain_score"] = self.df["clean_text"].apply(calc_pain)
        self.df["urgency_score"] = self.df["clean_text"].apply(calc_urgency)

        # 3. Engagement Score (log scaled upvotes + comments)
        self.df["engagement_score"] = np.round(
            np.log1p(self.df["score"]) * 1.5 + np.log1p(self.df["comments"]) * 2.0, 2
        )
        max_eng = self.df["engagement_score"].max()
        if max_eng > 0:
            self.df["engagement_normalized"] = np.round((self.df["engagement_score"] / max_eng) * 10.0, 2)
        else:
            self.df["engagement_normalized"] = 5.0

        # 4. Composite Priority / Opportunity Index (0 - 100)
        # Weighted combination of pain (40%), urgency (30%), engagement (30%)
        self.df["composite_priority"] = np.round(
            (self.df["pain_score"] * 4.0) +
            (self.df["urgency_score"] * 3.0) +
            (self.df["engagement_normalized"] * 3.0),
            1
        )

        return self.df

    def cluster_topics(self, n_clusters: int = 4) -> pd.DataFrame:
        """Use TF-IDF + MiniBatchKMeans to cluster problems into coherent categories."""
        if len(self.df) < n_clusters or len(self.df) < 3:
            self.df["cluster_id"] = 0
            self.df["cluster_label"] = "General Problem Space"
            return self.df

        try:
            vectorizer = TfidfVectorizer(
                max_features=200,
                stop_words="english",
                ngram_range=(1, 2)
            )
            tfidf_matrix = vectorizer.fit_transform(self.df["clean_text"])

            k = min(n_clusters, len(self.df))
            kmeans = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=64, n_init=3)
            self.df["cluster_id"] = kmeans.fit_predict(tfidf_matrix)

            # Extract top 2 terms per cluster for label
            feature_names = np.array(vectorizer.get_feature_names_out())
            labels_map = {}
            for i in range(k):
                center = kmeans.cluster_centers_[i]
                top_indices = center.argsort()[-3:][::-1]
                top_words = [feature_names[idx] for idx in top_indices if idx < len(feature_names)]
                labels_map[i] = " & ".join(top_words).title() if top_words else f"Cluster {i+1}"

            self.df["cluster_label"] = self.df["cluster_id"].map(labels_map)
        except Exception as e:
            logger.warning(f"Clustering skipped: {e}")
            self.df["cluster_id"] = 0
            self.df["cluster_label"] = "Problem Opportunity"

        return self.df

    def get_top_opportunities(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Return the highest ranked real-world problem opportunities formatted for projects."""
        if self.df.empty:
            return []

        if "composite_priority" not in self.df.columns:
            self.compute_metrics()

        if "cluster_id" not in self.df.columns:
            self.cluster_topics()

        sorted_df = self.df.sort_values(by="composite_priority", ascending=False).head(top_n)

        results = []
        for _, row in sorted_df.iterrows():
            # Derive feasibility and difficulty
            composite = float(row.get("composite_priority", 50.0))
            pain = float(row.get("pain_score", 5.0))
            
            # Difficulty inversely correlates with ease of building MVP
            difficulty = "Easy" if pain < 4.0 else ("Medium" if pain < 7.0 else "Challenging")
            feasibility = min(95, max(40, int(85 - (pain * 3))))

            results.append({
                "title": row.get("title"),
                "problem_statement": row.get("content")[:350] or row.get("title"),
                "platform": row.get("platform"),
                "source_url": row.get("url"),
                "author": row.get("author"),
                "subreddit": row.get("subreddit"),
                "cluster_label": row.get("cluster_label", "General Software Problem"),
                "metrics": {
                    "composite_priority": float(row.get("composite_priority", 0)),
                    "pain_intensity": float(row.get("pain_score", 0)),
                    "urgency_score": float(row.get("urgency_score", 0)),
                    "engagement_score": float(row.get("engagement_normalized", 0)),
                    "raw_upvotes": int(row.get("score", 0)),
                    "raw_comments": int(row.get("comments", 0)),
                },
                "project_potential": {
                    "viability_score": int(min(98, composite)),
                    "feasibility_score": feasibility,
                    "difficulty": difficulty,
                    "target_audience": f"Users of {row.get('platform', 'tech platforms')} dealing with {row.get('cluster_label', 'workflow challenges')}",
                    "suggested_solution": f"Automated AI-assisted tool or SaaS solving: {row.get('title')[:120]}",
                }
            })

        return results

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Generate high-level statistical summary using Pandas."""
        if self.df.empty:
            return {
                "total_items": 0,
                "platforms": {},
                "avg_pain_score": 0.0,
                "avg_urgency_score": 0.0,
                "highest_priority_score": 0.0,
            }

        if "composite_priority" not in self.df.columns:
            self.compute_metrics()

        platform_counts = self.df["platform"].value_counts().to_dict()

        return {
            "total_items": int(len(self.df)),
            "platforms": platform_counts,
            "avg_pain_score": round(float(self.df["pain_score"].mean()), 2),
            "avg_urgency_score": round(float(self.df["urgency_score"].mean()), 2),
            "avg_engagement_normalized": round(float(self.df["engagement_normalized"].mean()), 2),
            "highest_priority_score": round(float(self.df["composite_priority"].max()), 2),
            "top_subreddits": self.df[self.df["subreddit"] != ""]["subreddit"].value_counts().head(5).to_dict(),
        }

    def export_csv(self) -> str:
        """Export the analyzed dataset to CSV format for data scientists."""
        return self.df.to_csv(index=False)

    def export_json(self) -> str:
        """Export the analyzed dataset to JSON."""
        return self.df.to_json(orient="records", date_format="iso")
