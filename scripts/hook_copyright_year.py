""" Alter config on run
 https://www.mkdocs.org/user-guide/configuration/#hooks
 """
from datetime import datetime


def on_config(config, **kwargs):
    config.copyright = f"Copyright © {datetime.now().year} Your Name"
    config.copyright = (f'Copyright © 2024{"-" + str(datetime.now().year) if datetime.now().year > 2024 else ""} Pioneers Hub gGmbH – '
                        f'<a href="#__consent">Change cookie settings</a>')
