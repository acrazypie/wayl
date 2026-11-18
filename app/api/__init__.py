from flask_restful import Api

from app.api.auth import (
    ForgotPassword,
    Login,
    Logout,
    RefreshToken,
    Register,
    ResetPassword,
    SessionInfo,
)
from app.api.instance import InstanceInfo
from app.api.music import (
    ArtistDetail,
    ArtistSearch,
    HistoryList,
    PlaylistDetail,
    PlaylistList,
    PlaylistSongDetail,
    SavedSongDetail,
    SavedSongList,
    SongDetail,
    SongSearch,
    Stats,
)
from app.api.servers import (
    LibrarySearch,
    LibraryTrackMatch,
    ListenTokenResource,
    PlexPin,
    PlexPinCheck,
    ServerDetail,
    ServerList,
    ServerSync,
    SongSources,
    UnmatchedListens,
)
from app.api.sharing import MySharing, MySharingReset, PlaylistShare, PlaylistShareReset
from app.api.user import ChangePassword, Me, UserPlaylists, UserProfile
from app.utility import social_enabled

API_V1 = "/api/v1"


def versioned(path):
    """The stable /api/v1 twin of a route: /api/x -> /api/v1/x, /auth/x -> /api/v1/auth/x."""
    if path.startswith("/api/"):
        return API_V1 + path[len("/api"):]
    return API_V1 + path


def register_routes(app):
    """Add every REST resource to `app`. Each one is served at its usual path (what the web app
    uses) and under /api/v1 (what other clients should use)."""
    api = Api()  # one per app, so create_app() can be called more than once (tests)

    def add(resource, path, **kwargs):
        api.add_resource(resource, path, versioned(path), **kwargs)

    # Resources must be added BEFORE init_app, otherwise Flask-RESTful never registers them.
    add(InstanceInfo, "/api/instance")

    add(SessionInfo, "/auth/session")
    add(Register, "/auth/register")
    add(Login, "/auth/login")
    add(Logout, "/auth/logout")
    add(ForgotPassword, "/auth/forgot")
    add(ResetPassword, "/auth/reset")
    add(RefreshToken, "/auth/refresh")

    add(Me, "/api/me")
    add(ChangePassword, "/api/me/password")
    add(SavedSongList, "/api/me/songs")
    add(SavedSongDetail, "/api/me/songs/<string:song_id>")
    add(ListenTokenResource, "/api/me/listen-token")
    add(UnmatchedListens, "/api/me/unmatched")

    add(UserProfile, "/api/users/<int:user_id>")
    add(UserPlaylists, "/api/users/<int:user_id>/playlists")

    add(SongSearch, "/api/songs")
    add(SongDetail, "/api/songs/<string:song_id>")
    add(SongSources, "/api/songs/<string:song_id>/sources")
    add(ArtistSearch, "/api/artists")
    add(ArtistDetail, "/api/artists/<string:artist_id>")

    add(ServerList, "/api/servers")
    add(PlexPin, "/api/servers/plex/pin")
    add(PlexPinCheck, "/api/servers/plex/pin/<int:pin_id>")
    add(ServerDetail, "/api/servers/<int:server_id>")
    add(ServerSync, "/api/servers/<int:server_id>/sync")
    add(LibrarySearch, "/api/library")
    add(LibraryTrackMatch, "/api/library/tracks/<int:track_id>/match")

    add(PlaylistList, "/api/playlists")
    add(PlaylistDetail, "/api/playlists/<int:playlist_id>")
    add(PlaylistSongDetail, "/api/playlists/<int:playlist_id>/songs/<string:song_id>")
    add(PlaylistShare, "/api/playlists/<int:playlist_id>/share")
    add(PlaylistShareReset, "/api/playlists/<int:playlist_id>/share/reset")
    add(MySharing, "/api/me/sharing")
    add(MySharingReset, "/api/me/sharing/reset")
    add(HistoryList, "/api/history")
    add(Stats, "/api/stats")

    with app.app_context():
        social = social_enabled()
    if social:
        from app.api.social import register_social_routes

        register_social_routes(add)

    api.init_app(app)
    return api
