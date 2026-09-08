# OpenRGB integration path

OpenRGB does not currently have confirmed native support for the X68HE's `3151:502D`
controller. Its SDK exposes devices that the OpenRGB server already detects; it cannot add
hardware support by itself.

The current X68HE capture checkpoint does not satisfy the prerequisite for native support:
mode 21 is a volatile whole-keyboard colour report, while arbitrary per-key Light Edit
updates use flash-backed `0x0C` pages. The Python API therefore remains preset-only and no
OpenRGB controller is added yet.

After a volatile frame protocol passes hardware validation:

1. Add a dedicated HID detector for `3151:502D`, interface 2, usage page `0xFFFF`, usage 2.
2. Read `0x8F` and accept only X68HE internal IDs `2270`, `2472`, and `2902`.
3. Port the captured encoder and verified physical LED map to a native C++ controller.
4. Expose the verified physical LED layout and only confirmed built-in modes. The connected
   revision reports the vendor's 66-key layout despite the X68HE product name.
5. Add capture-derived tests and validate each hardware revision available to maintainers.

Do not attach this PID blindly to the existing Attack Shark K86/Epomaker controller. The
related devices reuse ROYUAN hardware but can use colliding opcodes and different command
families.

References:

- https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/2407
- https://gitlab.com/CalcProgrammer1/OpenRGB/-/work_items/5703
- https://gitlab.com/CalcProgrammer1/OpenRGB/-/raw/master/Documentation/OpenRGBSDK.md
