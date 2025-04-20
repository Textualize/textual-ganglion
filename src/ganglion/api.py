from __future__ import annotations

from collections import defaultdict
import logging

from aiohttp.web import Request, Response, json_response
from pydantic import ValidationError

from .context import get_server
from .api_models import Signup
from . import db

log = logging.getLogger("ganglion")


def _get_error(error_details: dict) -> str:
    if "ctx" in error_details and "error" in error_details["ctx"]:
        return str(error_details["ctx"]["error"])
    return error_details.get("msg", "")


async def signup(request: Request) -> Response:
    from rich import print

    data = await request.post()

    errors: defaultdict[str, list[str]] = defaultdict(list)

    try:
        signup = Signup(**data)
    except ValidationError as error:
        for validation_error in error.errors(include_url=False):
            if "loc" in validation_error and validation_error["loc"]:
                errors[validation_error["loc"][0]].append(_get_error(validation_error))
            else:
                errors["_"].append(validation_error["msg"])
        response = {"type": "fail", "errors": errors}
        return json_response(response)

    server = get_server()

    async with server.db_session() as session:
        if not (await db.check_email(signup.email)):
            errors["email"].append("Email is taken")
        if not (await db.check_account_slug(signup.account_slug)):
            errors["account_slug"].append(
                "Sorry, this slug is already reserved. Please pick another."
            )

        if errors:
            response = {"type": "fail", "errors": errors}
        else:
            try:
                user = await db.create_user(signup.name, signup.email, signup.password)
                _account, api_key = await db.create_account(
                    signup.name, signup.account_slug, [user]
                )
                auth_token = await db.login_user(user)
            except Exception as error:
                log.exception("failed to create new account")
                response = {
                    "type": "fail",
                    "error": "Signup failed, due to a server error. Please try again later.",
                }
                await session.rollback()
            else:
                response = {
                    "type": "success",
                    "user": {"email": signup.email},
                    "auth_token": {"key": auth_token.token},
                    "api_key": {"key": api_key.key},
                }

    print(response)
    return json_response(response)
