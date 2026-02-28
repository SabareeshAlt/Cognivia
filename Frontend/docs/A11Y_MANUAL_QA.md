# Manual Accessibility QA Script

## Keyboard-only checks
1. Navigate auth flow using Tab/Shift+Tab/Enter only.
2. Verify focus indicator is visible on all actionable controls.
3. Confirm dialogs can be opened/closed via keyboard.

## Screen reader smoke checks
1. Auth form inputs announce label + error state.
2. Chat input announces label and disabled state when offline.
3. Confirm buttons and destructive actions have meaningful names.

## Motion and contrast checks
1. Enable OS reduced-motion; verify UI animations are minimized.
2. Toggle `.high-contrast` class on `<body>` and verify readability.

## Release gate
- Any critical issue blocks release.
