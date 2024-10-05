"""
Script to manually add the Pioneers Hub logo to the social cards of website.
This is not supported by the open version of mkdocs-material, yet.
"""
from itertools import chain
from pathlib import Path

from omegaconf import OmegaConf
from PIL import Image

def on_post_build(config):
    # Importing conf is not working in CI
    conf = OmegaConf.load(Path(__file__).parents[1] / "config.yaml")
    # make dirs in config to Path objects
    conf.dirs["root"] = Path(__file__).parents[1]
    for k, dir_from_project_root in conf.dirs.items():
        conf.dirs[k] = conf.dirs["root"] / dir_from_project_root

    path_to_logo = conf.dirs.root / Path(conf.mkdocs.logo_path)
    path_to_social_cards_cache = conf.dirs.root / Path(conf.mkdocs.social_cards.cache_dir)
    path_to_social_cards_site = conf.dirs.root / Path(conf.mkdocs.social_cards.site_dir)

    the_logo = Image.open(path_to_logo)
    the_logo_position = (960, 450)
    base_width = 175
    ph_logo = Image.open(path_to_logo)
    w_percent = (base_width / ph_logo.size[0])
    h_size = int(float(ph_logo.size[1]) * float(w_percent))
    ph_logo = ph_logo.resize((base_width, h_size), Image.Resampling.LANCZOS)

    for social_card in chain(path_to_social_cards_cache.glob('*.png'), path_to_social_cards_site.glob('*.png')):
        # Get the social card image
        social_card_image = Image.open(social_card)

        # Paste the Pioneers Hub logo onto the social card image
        social_card_image.paste(ph_logo, the_logo_position, mask=ph_logo)

        # Save the new social card image
        social_card_image.save(social_card, quality=95)

