#!/bin/sh
set -eu
# Fixed names match the limited sudoers rule; never expand arbitrary /tmp files.
for name in apply_unknown_album_tag_plan export_unknown_album_discids fix_multidisc_albums inventory_unknown_albums normalize_unknown_album_tags query_gnudb test_fix_multidisc_albums verify_unknown_album_state; do
    test -f "/tmp/$name.py"
    /usr/bin/python3 -c 'import sys; compile(open(sys.argv[1], "rb").read(), sys.argv[1], "exec")' "/tmp/$name.py"
done
for name in apply_unknown_album_tag_plan export_unknown_album_discids fix_multidisc_albums inventory_unknown_albums normalize_unknown_album_tags query_gnudb test_fix_multidisc_albums verify_unknown_album_state; do
    sudo -n /bin/mv "/tmp/$name.py" "/volume1/scripts/$name.py"
    sudo -n /bin/chown root:root "/volume1/scripts/$name.py"
    sudo -n /bin/chmod 755 "/volume1/scripts/$name.py"
done
