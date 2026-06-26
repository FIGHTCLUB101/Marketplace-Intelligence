# ML Plan — Extracting Maximum Knowledge from `magicbricks_localities.xlsx`

> **Goal:** Derive every usable feature and insight from the 600-locality dataset — from existing
> columns and from new features engineered/learned from them — using machine learning, and feed the
> result back into the GOAT-Fit "Where to Win" engine. **Everything lives in `notebooks/`.**

---

## 0. Honest framing (what ML can and can't do here)

| Constraint | Implication for the plan |
|---|---|
| **600 rows** | Classical ML + pretrained embeddings only. No training deep nets from scratch. Always cross-validate; prefer regularized/tree models; report uncertainty. |
| **No native target label** | Lead with **unsupervised** (clustering, embeddings, topic modelling, anomaly) + **self-supervised** structure. Supervised tasks use *derived* targets (e.g. predict price from amenities) for **imputation** and **driver analysis**, not prediction-for-its-own-sake. |
| **Text-heavy** (5 free-text columns) | NLP is the biggest untapped value: NER, keyword/topic extraction, sentence embeddings, zero-shot sector tagging. |
| **Price missing 41.5%** | A legitimate, high-value ML task: **model-based imputation** with explicit confidence flags. |
| **Spatial (lat/lng) + graph (nearby localities)** | Geospatial clustering + a locality adjacency **graph** unlock features no single row contains. |

**Principle:** every derived feature must earn its place by serving a GOAT Life decision (where to push, who to target, what channel). No features for vanity.

---

## Pipeline shape

```
magicbricks_localities.xlsx
  -> 01 clean & structure          -> localities_clean.parquet
  -> 02 deterministic feature eng  -> features_base.parquet
  -> 03 NLP / text mining          -> features_text.parquet  (+ embeddings.npy)
  -> 04 geospatial + graph         -> features_geo_graph.parquet
  -> 05 unsupervised structure     -> localities_segmented.parquet (+ models, plots)
  -> 06 supervised: imputation+drivers -> features_imputed.parquet (+ SHAP)
  -> 07 similarity, anomaly, synthesis -> localities_features_master.parquet (+ insights.md)
```
Each notebook reads the previous artifact and appends columns — a reproducible feature store.
Final `localities_features_master.parquet` is the single source the GOAT-Fit pipeline can consume.

---

## Notebook 01 — `01_clean_structure.ipynb`
**Builds on the existing `magicbricks_cleaning.ipynb`.**
- Reuse/extend the reviewed cleaner: price → min/max/avg buy & rent; amenity counts; text normalisation; string pincode.
- Add geocoding (pgeocode) so every later notebook has `lat/lng`.
- **Output:** `localities_clean.parquet` (600 × ~30).
- **Validation:** parse-rate report, dtype audit, missingness matrix (`missingno`).

## Notebook 02 — `02_feature_engineering.ipynb`  *(deterministic, no ML yet)*
Derive new numeric features from existing ones — the raw material every model needs.
- **Price-derived:** `buy_rent_ratio` (rental-yield proxy), `price_spread = max−min` (heterogeneity/uncertainty), `affluence_tier` (quantile bins).
- **Amenity-derived:** `total_amenities`, `amenity_diversity` (Shannon entropy across the 7 types), `infra_completeness` (share of amenity types present), `retail_vs_resi_balance`.
- **Interaction features:** affluence×fitness, corporate×youth, etc. (for downstream models).
- **Output:** `features_base.parquet`.
- **Validation:** distributions, correlation heatmap, drop/flag near-constant or leaky features.

## Notebook 03 — `03_text_mining.ipynb`  *(NLP — the biggest win)*
Turn the 5 free-text columns (intro, employment, social infra, physical infra, commercial) into structured signal.
- **NER + keyword extraction:** spaCy (`en_core_web_sm`) + KeyBERT/RAKE → named employers, brands, sectors.
- **Zero-shot sector tagging:** `transformers` zero-shot (`facebook/bart-large-mnli`) → tag each locality's employment text with {IT/ITeS, Finance, Consulting, Manufacturing, Govt, Retail} → `sector_*` flags. *(Recommended; lightweight fallback = curated keyword lists if we want to avoid the model download.)*
- **Sentence embeddings:** `sentence-transformers` (`all-MiniLM-L6-v2`, 384-d) on each text column → dense vectors. Saved to `embeddings.npy`.
- **Topic modelling:** BERTopic (or LDA fallback) on locality intros → themes (e.g. "emerging/under-construction" vs "established premium") → `topic_id`, `topic_label`.
- **Derived flags from text:** `is_metro_connected`, `airport_min`, `maturity` (established/emerging via intro language).
- **Output:** `features_text.parquet` + `embeddings.npy`.
- **Validation:** sample-check NER hits; topic coherence score; manual spot-check of 10 localities.
- **Caveat:** zero-shot/embeddings are pretrained on global text — verify a sample by hand; flag low-confidence tags.

## Notebook 04 — `04_geo_graph.ipynb`  *(geospatial + graph ML)*
Extract features that live *between* localities, not within one row.
- **Geospatial:** distance-to-city-centroid, k-NN density (DBSCAN/`BallTree`), spatial cluster id (DBSCAN on lat/lng).
- **Adjacency graph:** build a graph from the `Nearby Localities` column (`networkx`).
  - Node features: degree/centrality (how connected), `pagerank`.
  - **Community detection** (Louvain) → contiguous "belts" → `belt_id` (directly serves "attack this belt").
  - **node2vec** embeddings (optional) → structural similarity.
- **Output:** `features_geo_graph.parquet`.
- **Validation:** map the spatial clusters + belts; sanity-check that known adjacent sectors land together.

## Notebook 05 — `05_unsupervised_segmentation.ipynb`  *(let the data define the archetypes)*
Replace the hand-coded archetypes with data-driven ones.
- **Assemble** the full feature matrix (base + text-embeddings + geo/graph); scale; **PCA** for denoising.
- **Cluster:** KMeans (elbow + silhouette) **and** HDBSCAN (density, finds noise) — compare.
- **Reduce for viz:** UMAP / t-SNE 2-D plot, colored by cluster, sized by affluence.
- **Profile each cluster:** mean feature deltas → name the data-driven personas (e.g. "Premium IT Corridor", "Emerging Value Belt", "Student/Education Hub", "Established Family Residential").
- **Output:** `localities_segmented.parquet` (+ cluster model `.joblib`, plots).
- **Validation:** silhouette score, cluster stability across seeds/subsamples, cross-tab vs the rule-based archetype as a sanity check.
- **GOAT value:** data-driven segments → sharper channel routing than hand rules.

## Notebook 06 — `06_supervised_imputation_drivers.ipynb`  *(supervised, with derived targets)*
Two honest supervised uses — fill gaps and explain drivers.
- **(a) Price imputation:** target = `res_avg_buy` (present 351 rows). Features = amenities + text flags + embeddings + geo (no target leakage). Model = LightGBM/RandomForest with **nested CV**; report R²/MAE honestly. Predict the 249 missing → `res_avg_buy_imputed` + `price_is_imputed` flag + prediction interval. **Never silently overwrite** real values.
- **(b) Driver analysis:** **SHAP** on the price model → which amenities/sectors/text themes most drive affluence. This *is* knowledge extraction ("metro access + IT employers + low price-spread predict premium").
- **Output:** `features_imputed.parquet` + SHAP summary plots.
- **Caveat:** with 351 training rows, treat imputation as *directional*; surface confidence everywhere; compare against the city mean as a baseline so we know the model actually adds signal.

## Notebook 07 — `07_similarity_anomaly_synthesis.ipynb`  *(applications + handoff)*
Turn features into GOAT-Life-usable tools and consolidate.
- **Lookalike engine:** cosine k-NN on the combined embedding+feature space → "find localities like Sohna Road" (lookalike expansion in other cities).
- **Anomaly detection:** IsolationForest → hidden gems (high latent affluence, low current attention) and data-quality outliers.
- **Re-derive GOAT-Fit** using the enriched, imputed, data-driven features (compare to the current rule-based score; quantify what changed and why).
- **Output:** `localities_features_master.parquet` (the consolidated feature store) + `insights.md` (top findings, ranked opportunities) — the artifact the production `pipeline/` can ingest.
- **Validation:** compare ML-GOAT-Fit vs rule-GOAT-Fit per city; list the localities that move the most and explain each.

---

## Libraries (add to a `notebooks/requirements-ml.txt`)
`scikit-learn, lightgbm, shap, sentence-transformers, transformers, bertopic, umap-learn, hdbscan,
spacy (+ en_core_web_sm), keybert, networkx, python-louvain, node2vec, geopy, missingno, pyarrow,
matplotlib, seaborn`
*(Lightweight path: drop transformers/bertopic/node2vec and use TF-IDF + LDA + keyword lists if we want zero large model downloads.)*

## Cross-cutting discipline
- **Reproducibility:** fixed seeds; each notebook reads/writes parquet; models saved with `joblib`.
- **No leakage:** imputation features exclude anything derived from the target.
- **Validation everywhere:** silhouette/stability for clusters, nested CV for supervised, manual spot-checks for NLP.
- **Confidence flags:** every imputed/inferred value carries an `*_is_imputed` / confidence field — same discipline as QCompass.
- **Small-N humility:** prefer simple models; report when a model fails to beat a baseline and say so.

## Decision for you
- **Path A (recommended): full NLP stack** — sentence-transformers + zero-shot + BERTopic (richer, ~a few hundred MB of model downloads).
- **Path B: lightweight** — TF-IDF + LDA + curated keyword lists (no big downloads, faster, slightly less semantic depth).

Pick A or B and I'll build Notebook 01 first, then proceed notebook-by-notebook with checkpoints.
