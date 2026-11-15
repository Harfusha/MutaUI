# Third-Party Notices and Redistribution Attributions

MutaUI (Mutagen Control) interacts with third-party software and libraries:

## Core Dependencies
1. **PySide6-Essentials** (The Qt Company Ltd.)
   - License: GNU Lesser General Public License version 3 (LGPLv3).
   - Dynamically linked; MutaUI does not statically link or modify Qt/PySide binaries.
2. **Paramiko** (Jeff Forcier and contributors)
   - License: GNU Lesser General Public License version 2.1 (LGPLv2.1).
   - Used for optional, read-only remote configuration inspection upon explicit operator action.
3. **ruamel.yaml** (Anthon van der Neut)
   - License: MIT License.
   - Used for lossless, comment-preserving YAML editing.
4. **psutil** (Giampaolo Rodola and contributors)
   - License: BSD 3-Clause License.
   - Used for non-invasive process and system resource monitoring.

## External Tooling
- **Mutagen CLI** (Havoc Inc. / mutagen-io contributors)
   - License: Server Side Public License (SSPL) / GPL depending on upstream version.
   - **Important:** MutaUI does NOT bundle or redistribute the Mutagen CLI binary in its source repository or application distribution packages. The user installs and provides their own Mutagen CLI on the local system. MutaUI executes the local CLI via standard subprocess invocations without embedding upstream code.

## License Decision
The repository owner reserves the explicit selection of the project's primary open-source or commercial license. Until formally designated by the owner, all rights are reserved.
