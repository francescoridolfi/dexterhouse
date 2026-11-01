# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point of the `dexterhouse` script."""

import typer

from dexterhouse import __version__
from dexterhouse.cli.pkg import app as pkg_app

app = typer.Typer(name="dexterhouse", help="DexterHouse command line.", no_args_is_help=True)
app.add_typer(pkg_app, name="pkg")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
) -> None:
    if version:
        typer.echo(f"dexterhouse {__version__}")
        raise typer.Exit()
