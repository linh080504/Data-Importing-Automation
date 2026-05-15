from app.db.session import SessionLocal
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.services.direct_run import run_crawl_job_direct, _build_progress


def main():
    db = SessionLocal()
    try:
        template = db.query(CleanTemplate).first()
        if not template:
            template = CleanTemplate(
                template_name="_tmp_vn_template",
                file_name="_tmp_vn.csv",
                column_count=2,
                columns=[{"field": "name"}, {"field": "website"}],
            )
            db.add(template)
            db.commit()
            db.refresh(template)
            print("Created temporary clean template:", template.id)
        else:
            print("Using existing template:", template.id)

        job = CrawlJob(
            country="Vietnam",
            source_ids=[],
            crawl_mode="trusted_sources",
            discovery_input=None,
            critical_fields=["name", "website"],
            clean_template_id=template.id,
            ai_assist=False,
            progress=_build_progress(total_records=0, crawled=0, extracted=0, needs_review=0, cleaned=0),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print("Created crawl job:", job.id)

        result = run_crawl_job_direct(db, job=job)
        print("Run finished. Summary:\n", result)
        print("Final job progress:\n", job.progress)
    finally:
        db.close()


if __name__ == "__main__":
    main()
