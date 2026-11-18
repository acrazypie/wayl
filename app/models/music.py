"""Local copies of catalog entries.

Songs come from MusicBrainz/ListenBrainz (CC0 metadata). A row is stored the first time
someone logs, saves or adds that song, so history, playlists and stats can join on it.
Public ids are MusicBrainz ids (mbid); the integer ids stay internal.
"""
from app.models import db, utcnow


class Artist(db.Model):
    __tablename__ = "artists"
    id = db.Column(db.Integer, primary_key=True)
    mbid = db.Column(db.String(36), unique=True, nullable=True)
    name = db.Column(db.String(300), nullable=False)
    songs = db.relationship("Song", backref="artist", lazy=True)


class Album(db.Model):
    __tablename__ = "albums"
    id = db.Column(db.Integer, primary_key=True)
    mbid = db.Column(db.String(36), unique=True, nullable=True)  # MusicBrainz release id
    title = db.Column(db.String(300), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    cover_url = db.Column(db.String(300), nullable=True)
    songs = db.relationship("Song", backref="album", lazy=True)


class Song(db.Model):
    __tablename__ = "songs"
    id = db.Column(db.Integer, primary_key=True)
    mbid = db.Column(db.String(36), unique=True, nullable=False)  # MusicBrainz recording id
    title = db.Column(db.String(300), nullable=False)
    duration = db.Column(db.Integer)  # seconds
    genre = db.Column(db.String(100))
    artist_id = db.Column(db.Integer, db.ForeignKey("artists.id"), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey("albums.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.mbid,
            "title": self.title,
            "artist": self.artist.name if self.artist else None,
            "artist_id": self.artist.mbid if self.artist else None,
            "album": self.album.title if self.album else None,
            "year": self.album.year if self.album else None,
            "cover": self.album.cover_url if self.album else None,
            "genre": self.genre,
            "duration": self.duration,
        }


class Playlist(db.Model):
    __tablename__ = "playlists"
    __table_args__ = (db.Index("ix_playlists_share_token", "share_token", unique=True),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # is_public: visible to signed-in users of *this* instance.
    # share_token: a read-only link anyone can open, from anywhere (see docs/sharing-protocol.md).
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    share_token = db.Column(db.String(32), nullable=True)  # unique: see the index above
    created_at = db.Column(db.DateTime, default=utcnow)
    songs = db.relationship(
        "PlaylistSong",
        backref="playlist",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="PlaylistSong.id",
    )


class PlaylistSong(db.Model):
    __tablename__ = "playlist_songs"
    __table_args__ = (db.UniqueConstraint("playlist_id", "song_id"),)

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlists.id"), nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=utcnow)
    song = db.relationship("Song")


class SavedSong(db.Model):
    """A song in someone's library ("My songs")."""

    __tablename__ = "saved_songs"
    __table_args__ = (db.UniqueConstraint("user_id", "song_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    song = db.relationship("Song")


class ListeningHistory(db.Model):
    __tablename__ = "listening_history"
    __table_args__ = (db.Index("ix_history_user_time", "user_id", "listened_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id"), nullable=False)
    listened_at = db.Column(db.DateTime, default=utcnow)  # callable, evaluated per row
    # Where it came from: None (logged by hand), "player", "plex", "navidrome", "scrobbler"
    source = db.Column(db.String(30), nullable=True)
    song = db.relationship("Song")
