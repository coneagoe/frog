import os
import conf
conf.parse_config()
from app import db, create_app, scheduler, add_job_monitor_stock


app = create_app(os.environ['FROG_SERVER_CONFIG'])

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    scheduler.start()
    add_job_monitor_stock()
    app.run()
