# Design

## System Overview

The interface is a product tool for high-frequency exam practice. Use a restrained, light study palette anchored by oxidized teal-green. The physical scene is a clean library table near daylight: focused, low-glare, quiet, and accurate.

## Color Tokens

Use OKLCH custom properties in CSS.

- `--bg`: `oklch(1 0 0)`
- `--surface`: `oklch(0.975 0.012 165)`
- `--surface-strong`: `oklch(0.94 0.035 165)`
- `--ink`: `oklch(0.19 0.028 170)`
- `--muted`: `oklch(0.43 0.032 170)`
- `--primary`: `oklch(0.45 0.086 170)`
- `--primary-strong`: `oklch(0.36 0.095 170)`
- `--accent`: `oklch(0.63 0.14 55)`
- `--success`: `oklch(0.50 0.13 150)`
- `--warning`: `oklch(0.68 0.15 75)`
- `--danger`: `oklch(0.55 0.17 25)`
- `--border`: `oklch(0.88 0.018 165)`

## Typography

Use one system sans stack: `Inter`, `Segoe UI`, `PingFang SC`, `Microsoft YaHei`, `system-ui`, `sans-serif`. Use fixed sizes, not viewport-fluid text. Keep question text readable with a maximum line length around 72 characters.

## Components

- App shell: compact top navigation, content area, status strip.
- Panels: 8px radius, full border, no nested decorative cards.
- Buttons: consistent height, clear active/focus/disabled states.
- Choice controls: native radio and checkbox inputs with large click targets.
- Feedback: inline result panel after submission, never browser alerts.
- Audit table: dense but readable, with source issue and handling status.

## Motion

Use 150-250ms transitions for button feedback, practice-panel changes, result reveal, and progress changes. Motion must communicate state. Disable transform-heavy effects under `prefers-reduced-motion: reduce`.

## Layout

Desktop uses a two-column practice layout: primary question surface and secondary progress/audit context. Mobile collapses to one column with sticky practice actions. Text, option labels, and controls must wrap cleanly without overlap.
