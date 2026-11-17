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

## Project License

The repository owner selected the MIT License for MutaUI's project-owned code on 2026-11-17. See LICENSE. This grant does not change third-party component terms.

## Qt and other LGPL components

- The pinned PySide6-Essentials 6.8.3 / Qt 6.8.3 runtime is used under the LGPLv3 option. The frozen builds dynamically link Qt libraries and do not modify Qt/PySide binaries.
- Paramiko 5.1.0 is distributed under LGPLv2.1. Full LGPL texts are provided in licenses/LGPL-3.0.txt and licenses/LGPL-2.1.txt.
- Qt's official obligations guidance: https://www.qt.io/development/open-source-lgpl-obligations
- Corresponding upstream sources: Qt 6.8.3 https://download.qt.io/official_releases/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz and PySide setup 6.8.3 https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=6.8.3

LGPL distribution review: PENDING

LGPLv3 redistribution also requires users to be able to replace/relink the library and run the modified application, with sufficient installation information. This has not been verified for every frozen package, especially the Windows one-file executable. Do not publish a binary release until the exact package set, corresponding source delivery, relinking/installation instructions, and written-offer requirements receive legal review.
