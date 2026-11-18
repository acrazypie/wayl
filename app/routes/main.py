from flask import Blueprint, render_template

main_bp = Blueprint("main_bp", __name__)

# Every page is rendered by the same single-page app; the browser picks the view from the URL.
PAGES = [
    "/",
    "/search",
    "/following",
    "/playlists",
    "/playlists/<int:playlist_id>",
    "/songs",
    "/profile",
    "/song/<string:song_id>",
    "/artist/<string:artist_id>",
    "/user/<int:user_id>",
    "/login",
    "/register",
    "/forgot",
    "/reset",
]


def page(**_kwargs):
    response = render_template("index.html")
    return response, 200, {"Referrer-Policy": "same-origin"}  # reset tokens stay out of Referer


for rule in PAGES:
    main_bp.add_url_rule(rule, view_func=page, endpoint="page:" + rule)
