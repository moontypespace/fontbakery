"""
Checks for Fontwerk <https://fontwerk.com/>
"""
from math import atan2, degrees
import math

from fontbakery.callable import check
from fontbakery.section import Section
from fontbakery.status import PASS, FAIL
from fontbakery.fonts_profile import profile_factory
from fontbakery.message import Message
from fontbakery.profiles.googlefonts import GOOGLEFONTS_PROFILE_CHECKS
from fontTools.varLib import instancer

profile_imports = ('fontbakery.profiles.googlefonts',)
profile = profile_factory(default_section=Section("Fontwerk"))

# FIXME: It would be much better to refactor this as described at:
#        https://github.com/googlefonts/fontbakery/issues/3585
profile.configuration_defaults = {
    "com.google.fonts/check/file_size": {
        "WARN_SIZE": 1 * 1024 * 1024,
        "FAIL_SIZE": 9 * 1024 * 1024
    }
}

# Note: I had to use a function here in order to display it
# in the auto-generated Sphinx docs due to this bug:
# https://stackoverflow.com/questions/31561895/literalinclude-how-to-include-only-a-variable-using-pyobject
def leave_this_one_out(checkid):
    CHECKS_NOT_TO_INCLUDE = [
        # don't run these checks on the Fontwerk profile:
        'com.google.fonts/check/canonical_filename',
        'com.google.fonts/check/vendor_id',
        'com.google.fonts/check/fstype',
        'com.google.fonts/check/gasp',

        # The following check they may need some improvements
        # before we decide to include it:
        'com.google.fonts/check/family/italics_have_roman_counterparts',
    ]

    if checkid in CHECKS_NOT_TO_INCLUDE:
        return True


FONTWERK_PROFILE_CHECKS = \
    [checkid for checkid in GOOGLEFONTS_PROFILE_CHECKS
     if not leave_this_one_out(checkid)] + [
        'com.fontwerk/check/no_mac_entries',
        'com.fontwerk/check/vendor_id',
        'com.fontwerk/check/weight_class_fvar',
        'com.fontwerk/check/inconsistencies_between_fvar_stat',
        'com.fontwerk/check/interpolation_issues',
    ]


def add_dict_set(d, item_dict, item_set):
    if item_dict not in d:
        d[item_dict] = set()
    d[item_dict].add(item_set)

    return d

def close_enough(value_a, value_b, tolerance=0.0):
    """
    General function for checking if a value
    is close enough to a different value.
    """
    return math.isclose(value_a, value_b, abs_tol=tolerance)

def get_degree_of_line(point_a, point_b):
    x = point_b[0] - point_a[0]
    y = point_b[1] - point_a[1]
    return degrees(atan2(y, x))

def normalize_degree(deg):
    if deg < 0:
        return deg + 360
    return deg

@check(
    id = 'com.fontwerk/check/no_mac_entries',
    rationale = """
        Mac name table entries are not needed anymore.
        Even Apple stopped producing name tables with platform 1.
        Please see for example the following system font:
        /System/Library/Fonts/SFCompact.ttf

        Also, Dave Opstad, who developed Apple's TrueType specifications, told Olli Meier a couple years ago (as of January/2022) that these entries are outdated and should not be produced anymore.
    """,
    proposal = 'https://github.com/googlefonts/gftools/issues/469'
)
def com_fontwerk_check_name_no_mac_entries(ttFont):
    """Check if font has Mac name table entries (platform=1)"""

    passed = True
    for rec in ttFont["name"].names:
        if rec.platformID == 1:
            yield FAIL,\
                  Message("mac-names",
                          f'Please remove name ID {rec.nameID}')
            passed = False

    if passed:
        yield PASS, 'No Mac name table entries.'


@check(
    id = 'com.fontwerk/check/vendor_id',
    rationale = """
        Vendor ID must be WERK for Fontwerk fonts.
    """,
    proposal = 'https://github.com/googlefonts/fontbakery/pull/3579'
)
def com_fontwerk_check_vendor_id(ttFont):
    """Checking OS/2 achVendID."""

    vendor_id = ttFont['OS/2'].achVendID
    if vendor_id != 'WERK':
        yield FAIL,\
              Message("bad-vendor-id",
                      f"OS/2 VendorID is '{vendor_id}', but should be 'WERK'.")
    else:
        yield PASS, f"OS/2 VendorID '{vendor_id}' is correct."


@check(
    id = 'com.fontwerk/check/weight_class_fvar',
    rationale = """
        According to Microsoft's OT Spec the OS/2 usWeightClass should match the fvar default value.
    """,
    conditions = ["is_variable_font"],
    proposal = 'https://github.com/googlefonts/gftools/issues/477'
)
def com_fontwerk_check_weight_class_fvar(ttFont):
    """Checking if OS/2 usWeightClass matches fvar."""

    fvar = ttFont['fvar']
    default_axis_values = {a.axisTag: a.defaultValue for a in fvar.axes}

    fvar_value = default_axis_values.get('wght', None)
    os2_value = ttFont["OS/2"].usWeightClass

    if fvar_value is None:
        return

    if os2_value != int(fvar_value):
        yield FAIL,\
              Message("bad-weight-class",
                      f"OS/2 usWeightClass is '{os2_value}', "
                      f"but should match fvar default value '{fvar_value}'.")

    else:
        yield PASS, f"OS/2 usWeightClass '{os2_value}' matches fvar default value."


def is_covered_in_stat(ttFont, axis_tag, value):
    stat_table = ttFont['STAT'].table
    for ax_value in stat_table.AxisValueArray.AxisValue:
        axis_tag_stat = stat_table.DesignAxisRecord.Axis[ax_value.AxisIndex].AxisTag
        if axis_tag != axis_tag_stat:
            continue

        stat_value = []
        if ax_value.Format in (1, 3):
            stat_value.append(ax_value.Value)

        if ax_value.Format == 3:
            stat_value.append(ax_value.LinkedValue)

        if ax_value.Format == 2:
            stat_value.append(ax_value.NominalValue)

        if ax_value.Format == 4:
            # TODO: Need to implement
            #  locations check as well
            pass

        if value in stat_value:
            return True

    return False


@check(
    id = 'com.fontwerk/check/inconsistencies_between_fvar_stat',
    rationale = """
        Check for inconsistencies in names and values between the fvar instances and STAT table.
        Inconsistencies may cause issues in apps like Adobe InDesign.
    """,
    conditions = ["is_variable_font"],
    proposal = 'https://github.com/googlefonts/fontbakery/pull/3636'
)
def com_fontwerk_check_inconsistencies_between_fvar_stat(ttFont):
    """Checking if STAT entries matches fvar and vice versa."""

    if 'STAT' not in ttFont:
        return FAIL,\
               Message("missing-stat-table",
                       "Missing STAT table in variable font.")

    fvar = ttFont['fvar']
    name = ttFont['name']

    for ins in fvar.instances:
        instance_name = name.getDebugName(ins.subfamilyNameID)
        if instance_name is None:
            yield FAIL,\
                  Message("missing-name-id",
                          f"The name ID {ins.subfamilyNameID} used in an "
                          f"fvar instance is missing in the name table.")
            continue

        for axis_tag, value in ins.coordinates.items():
            if not is_covered_in_stat(ttFont, axis_tag, value):
                yield FAIL,\
                      Message("missing-fvar-instance-axis-value",
                              f"{instance_name}: '{axis_tag}' axis value '{value}' "
                              f"missing in STAT table.")

        # TODO: Compare fvar instance name with constructed STAT table name.


@check(
    id = 'com.fontwerk/check/interpolation_issues',
    rationale = """
        Check for interpolation issues within a variable font,
        by checking the direction of the starting point.
    """,
    conditions = ["is_variable_font"],
    proposal = 'https://github.com/googlefonts/noto-fonts/issues/2261'
)
def com_fontwerk_check_interpolation_issues(ttFont):
    """Look for possible interpolation issues."""

    fvar = ttFont['fvar']

    font_instances = dict()
    for instance in fvar.instances:
        instance_font = instancer.instantiateVariableFont(ttFont, instance.coordinates)
        subfamilyname = ttFont['name'].getDebugName(instance.subfamilyNameID)
        font_instances[subfamilyname] = instance_font

    errs = dict()
    for g_name in ttFont.getGlyphOrder():
        glyphs = []
        for instance_name, font_instance in font_instances.items():
            glyphs.append(font_instance['glyf'].get(g_name, None))

        points_set = {len(g.coordinates) for g in glyphs if getattr(g, 'coordinates', None)}
        if not points_set:
            # skip because,
            # glyph seems to have no outlines at all.
            continue

        if len(points_set) > 1:
            errs = add_dict_set(errs, "Differences in 'coordinates' (number of points)", g_name)
            continue

        contours_set = {g.numberOfContours for g in glyphs if getattr(g, 'numberOfContours', None)}
        if len(contours_set) > 1:
            errs = add_dict_set(errs, "Differences in 'numberOfContours'", g_name)
            continue

        composite_set = {g.isComposite() for g in glyphs}
        if len(composite_set) > 1:
            errs = add_dict_set(errs, "Differences in 'isComposite'", g_name)
            continue

        components_set = {g.components for g in glyphs if getattr(g, 'components', None)}
        if len(components_set) > 1:
            errs = add_dict_set(errs, "Differences in 'components'", g_name)
            continue

        for i, g in enumerate(glyphs):
            if i == 0:
                # skip the first layer,
                # because compare with previous glyph
                # would not be possible
                continue

            previous_g = glyphs[i - 1]
            for n in g.endPtsOfContours:
                end_point = g.coordinates[n]
                before_end_point = g.coordinates[n-1]

                pre_end_point = previous_g.coordinates[n]
                pre_before_end_point = previous_g.coordinates[n-1]

                deg = get_degree_of_line(before_end_point, end_point)
                pre_deg = get_degree_of_line(pre_before_end_point, pre_end_point)
                if close_enough(deg, pre_deg, tolerance=45):
                    # catch situations like -2.0 vs 0.0
                    continue

                if not close_enough(normalize_degree(deg), normalize_degree(pre_deg), tolerance=45):
                    errs = add_dict_set(errs, "Differences in end point direction (more than 45 degree)", g_name)
                    break

    if errs:
        for title in errs:
            yield FAIL, Message("interpolation-issues", f"{title}: {', '.join(list(errs[title]))}")
    else:
        yield PASS, "No interpolation issues found."


profile.auto_register(globals(),
                      filter_func=lambda type, id, _:
                      not (type == 'check' and leave_this_one_out(id)))
profile.test_expected_checks(FONTWERK_PROFILE_CHECKS, exclusive=True)
