from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


def current_time():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=current_time)

    directories = relationship(
        "Directory",
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    files = relationship("FileMetadata", back_populates="owner")


class Directory(Base):
    __tablename__ = "directories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("directories.id"), nullable=True)

    created_at = Column(DateTime, default=current_time)

    owner = relationship("User", back_populates="directories")

    parent = relationship(
        "Directory",
        remote_side=[id],
        backref="children"
    )

    files = relationship("FileMetadata", back_populates="directory")

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "parent_id",
            "name",
            name="unique_directory_per_parent"
        ),
    )


class FileMetadata(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), nullable=False)
    size = Column(BigInteger, default=0)
    sha256 = Column(String(64), nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    directory_id = Column(
        Integer,
        ForeignKey("directories.id"),
        nullable=False
    )

    version = Column(Integer, default=1)
    status = Column(String(30), default="ACTIVE")

    created_at = Column(DateTime, default=current_time)
    updated_at = Column(
        DateTime,
        default=current_time,
        onupdate=current_time
    )

    owner = relationship("User", back_populates="files")
    directory = relationship("Directory", back_populates="files")

    blocks = relationship(
        "Block",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="Block.block_index"
    )

    lock = relationship(
        "FileLock",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan"
    )

    versions = relationship(
        "FileVersion",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="FileVersion.version_number"
    )

    __table_args__ = (
        UniqueConstraint(
            "directory_id",
            "name",
            name="unique_file_per_directory"
        ),
    )


class Block(Base):
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, index=True)

    block_id = Column(String(128), unique=True, nullable=False, index=True)
    block_index = Column(Integer, nullable=False)

    size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)

    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)

    created_at = Column(DateTime, default=current_time)

    file = relationship("FileMetadata", back_populates="blocks")

    replicas = relationship(
        "BlockReplica",
        back_populates="block",
        cascade="all, delete-orphan"
    )

    version_references = relationship(
        "VersionBlock",
        back_populates="block",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "block_index",
            name="unique_block_position"
        ),
    )


class FileVersion(Base):
    __tablename__ = "file_versions"

    id = Column(Integer, primary_key=True, index=True)

    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    version_number = Column(Integer, nullable=False)

    size = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)

    status = Column(String(30), default="ACTIVE")
    created_at = Column(DateTime, default=current_time)

    file = relationship("FileMetadata", back_populates="versions")

    blocks = relationship(
        "VersionBlock",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="VersionBlock.block_index"
    )

    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "version_number",
            name="unique_file_version"
        ),
    )


class VersionBlock(Base):
    __tablename__ = "version_blocks"

    id = Column(Integer, primary_key=True, index=True)

    version_id = Column(
        Integer,
        ForeignKey("file_versions.id"),
        nullable=False
    )

    block_id = Column(
        Integer,
        ForeignKey("blocks.id"),
        nullable=False
    )

    block_index = Column(Integer, nullable=False)

    version = relationship("FileVersion", back_populates="blocks")
    block = relationship("Block", back_populates="version_references")

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "block_index",
            name="unique_version_block_position"
        ),
        UniqueConstraint(
            "version_id",
            "block_id",
            name="unique_version_block"
        ),
    )


class DataNode(Base):
    __tablename__ = "datanodes"

    id = Column(Integer, primary_key=True, index=True)

    node_id = Column(String(50), unique=True, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)

    status = Column(String(30), default="UNKNOWN")

    capacity = Column(BigInteger, default=0)
    used_space = Column(BigInteger, default=0)

    last_heartbeat = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=current_time)

    replicas = relationship("BlockReplica", back_populates="datanode")


class BlockReplica(Base):
    __tablename__ = "block_replicas"

    id = Column(Integer, primary_key=True, index=True)

    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    datanode_id = Column(Integer, ForeignKey("datanodes.id"), nullable=False)

    status = Column(String(30), default="ACTIVE")
    created_at = Column(DateTime, default=current_time)

    block = relationship("Block", back_populates="replicas")
    datanode = relationship("DataNode", back_populates="replicas")

    __table_args__ = (
        UniqueConstraint(
            "block_id",
            "datanode_id",
            name="unique_replica_per_node"
        ),
    )


class FileLock(Base):
    __tablename__ = "file_locks"

    id = Column(Integer, primary_key=True, index=True)

    file_id = Column(
        Integer,
        ForeignKey("files.id"),
        unique=True,
        nullable=False
    )

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    lock_token = Column(String(128), unique=True, nullable=False)

    acquired_at = Column(DateTime, default=current_time)
    expires_at = Column(DateTime, nullable=False)

    file = relationship("FileMetadata", back_populates="lock")


class WriteSession(Base):
    __tablename__ = "write_sessions"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(String(128), unique=True, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)

    # Versión que quedó asociada a la sesión al abrirla.
    version_id = Column(
        Integer,
        ForeignKey("file_versions.id"),
        nullable=True
    )

    status = Column(String(30), default="IN_PROGRESS")
    mode = Column(String(10), default="r")

    created_at = Column(DateTime, default=current_time)
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    version = relationship("FileVersion")