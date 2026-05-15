from app.db.session import SessionLocal
from app.models.data_source import DataSource
from app.models.crawl_job import CrawlJob
from app.services.direct_run import run_crawl_job_direct, _build_progress


def create_wikidata_source(db, country_name: str) -> DataSource:
    existing = db.query(DataSource).filter(DataSource.source_name == f"Wikidata {country_name}").one_or_none()
    if existing:
        return existing
    config = {
        "source_type": "wikidata_sparql",
        "url": "https://query.wikidata.org/sparql",
        "role": "reference",
        "trust_level": "high",
    }
    ds = DataSource(country=country_name, source_name=f"Wikidata {country_name}", supported_fields=["name", "country", "website"], config=config)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def run_for_country(country_name: str):
    db = SessionLocal()
    try:
        ds = create_wikidata_source(db, country_name)
        print("Using data source:", ds.id)
        job = CrawlJob(
            country=country_name,
            source_ids=[str(ds.id)],
            crawl_mode="trusted_sources",
            discovery_input=None,
            critical_fields=["name", "website"],
            clean_template_id=None,
            ai_assist=False,
            progress=_build_progress(total_records=0, crawled=0, extracted=0, needs_review=0, cleaned=0),
        )
        # Create job; note: clean_template_id must be valid — if none exists, create minimal placeholder. We'll fallback to using first template.
        if job.clean_template_id is None:
            from app.models.clean_template import CleanTemplate
            template = db.query(CleanTemplate).first()
            if not template:
                template = CleanTemplate(template_name="_tmp_wikidata_template", file_name="_tmp.csv", column_count=2, columns=[{"field":"name"},{"field":"website"}])
                db.add(template)
                db.commit()
                db.refresh(template)
            job.clean_template_id = template.id

        db.add(job)
        db.commit()
        db.refresh(job)
        print("Created crawl job:", job.id)

        result = run_crawl_job_direct(db, job=job)
        print("Import finished. Summary:\n", result)
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    country = sys.argv[1] if len(sys.argv) > 1 else "Vietnam"
    run_for_country(country)
