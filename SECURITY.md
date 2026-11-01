# Security

ReflektorTTS loads code into running games, reads their memory, downloads voices and translation models, and serves a local API, so security problems in it matter. Thank you for reporting them.

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub instead: open the repository's **Security** tab and choose **Report a vulnerability**. Describe what is affected, how to reproduce it, and what an attacker could do with it.

## What is in scope

- The local API on `127.0.0.1:47821`, including what a web page or another program on the same computer can make it do.
- The overlay DLL and the injector that loads it into games.
- Downloads: lists, archives and the files they install.
- Game profiles, which other players share: anything a crafted profile can make ReflektorTTS do.

## Supported versions

ReflektorTTS has not had a release yet; fixes go into the latest version on the main branch.
