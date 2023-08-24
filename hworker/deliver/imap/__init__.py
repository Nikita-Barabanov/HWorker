"""imap backend"""
import os
import re
import tarfile
import tempfile
import datetime
import traceback

from .mailer_utilities import get_mailbox
from ...config import get_imap_info, email_to_uid, deliverid_to_taskid
from ...log import get_logger
from ... import depot
from ...depot.objects import Homework

_default_datetime = datetime.datetime.fromisoformat("2009-05-17 20:09:00")
_depot_prefix = "i"


def parse_tar_file(filename: str, content: bytes):
    timestamps = []
    contents = {}
    is_broken = False

    try:
        with tempfile.NamedTemporaryFile("wb", delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()

        with tarfile.open(tmp_file.name) as tar:
            for member in tar.getmembers():
                member: tarfile.TarInfo
                if member.isfile():
                    timestamps.append(member.mtime)
                    contents[f"{filename}/{member.name}"] = tar.extractfile(member).read()

        os.remove(tmp_file.name)
    except Exception as e:
        is_broken = True
        get_logger(__name__).debug(f"Exception during archive parsing\n {''.join(traceback.format_exception(e))}")
    return max(timestamps, default=_default_datetime.timestamp()), contents, is_broken


def download_all():
    depot.store(depot.objects.UpdateTime(name="Imap deliver", timestamp=datetime.datetime.now().timestamp()))

    box = get_mailbox()

    # TODO maybe should only get new latter, not all. Fow know this works really fast, just skip it.
    # print(box.uids("ALL"))

    download_mails = 0

    get_logger(__name__).info(f"Started")

    for mail in box.fetch("ALL", limit=get_imap_info()["letter_limit"]):
        mail_name = mail.from_
        timestamps = []
        contents = {}
        is_broken_all = False

        deliver_ids = []

        for attachment in mail.attachments:
            deliver_id = re.findall(r"(?<=report\.).+(?=\.)", attachment.filename)
            deliver_id = deliver_id[0] if len(deliver_id) == 1 else None

            if deliver_id is not None:
                deliver_ids.append(deliver_id)

                timestamp, content, is_broken = parse_tar_file(filename=attachment.filename, content=attachment.payload)
                timestamps.append(timestamp)
                contents.update(content)
                is_broken_all = is_broken_all or is_broken

                get_logger(__name__).debug(f"Find {attachment.filename:<20} for email {mail_name:<30}")

        TASK_ID = None
        if len(deliver_ids) > 0:
            if all([name == deliver_ids[0] for name in deliver_ids]):
                TASK_ID = deliverid_to_taskid(deliver_ids[0])
            else:
                get_logger(__name__).debug(f"Detected multiple task for email {mail_name:<30}")

        USER_ID = email_to_uid(mail_name)

        if TASK_ID is not None:
            if USER_ID is None:
                get_logger(__name__).warn(f"Detected task {TASK_ID:<15} for not registered email {mail_name:<30}")
            else:
                depot.store(
                    Homework(
                        ID=f"{_depot_prefix}{mail.uid}",
                        USER_ID=USER_ID,
                        TASK_ID=TASK_ID,
                        timestamp=max(timestamps),
                        content=contents,
                        is_broken=is_broken_all,
                    )
                )
                download_mails += 1

    get_logger(__name__).info(f"Download a total of {download_mails} homeworks")
