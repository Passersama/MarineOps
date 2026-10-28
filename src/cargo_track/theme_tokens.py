"""Explicit semantic colors shared by the native stylesheet, palette and delegates."""
LIGHT = {
    'surface':'#FFFFFF','text':'#24262B','window':'#F5F5F7','divider':'#E5E5EA',
    'muted':'#666970','border':'#DCDDE2','hover':'#F0F3F8','hover_border':'#C2C9D5',
    'pressed':'#E7EDF5','disabled':'#8D9098','selection':'#EAF3FF','selection_text':'#0066CC',
    'selection_border':'#007AFF','menu_hover':'#E8EFF8','field_hover_border':'#BBC5D3',
    'field_hover':'#FAFBFD','field_disabled':'#858992','text_selection':'#D5E8FF',
    'focus':'#007AFF','tab_track':'#E9EAEE','tab_text':'#62656D','tab_hover':'#DFE2E8',
    'alternate':'#FAFAFC','header':'#6D7078','scrollbar':'#BFC2C9','scrollbar_hover':'#999DA6',
    'primary':'#0066D6','primary_hover':'#006BE0','primary_text':'#FFFFFF',
    'placeholder':'#65738A','error':'#B3261E','read_only':'#666970',
    'waiting_surface':'#FFF2D6','waiting_text':'#7A4B00',
    'onboard_surface':'#DFEDFF','onboard_text':'#174B87',
    'done_surface':'#E2F3E7','done_text':'#17603A',
    'logo_surface':'#F5F5F7','menu_selection_text':'#FFFFFF',
}
DARK = {
    'surface':'#20262D','text':'#E6E8ED','window':'#191E23','divider':'#343E49',
    'muted':'#ADB4C1','border':'#414650','hover':'#303744','hover_border':'#596578',
    'pressed':'#38475D','disabled':'#9299A6','selection':'#183D61','selection_text':'#A6D0FF',
    'selection_border':'#4199FF','menu_hover':'#38475D','field_hover_border':'#626C7D',
    'field_hover':'#30333B','field_disabled':'#9299A6','text_selection':'#315B83',
    'focus':'#4199FF','tab_track':'#262931','tab_text':'#B6BDCA','tab_hover':'#353B46',
    'alternate':'#202329','header':'#ADB4C1','scrollbar':'#626A78','scrollbar_hover':'#8993A3',
    'primary':'#0066D6','primary_hover':'#006BE0','primary_text':'#FFFFFF',
    'placeholder':'#A4ABB7','error':'#FFB4AB','read_only':'#ADB4C1',
    'waiting_surface':'#49381C','waiting_text':'#FFD58A',
    'onboard_surface':'#193957','onboard_text':'#A9D0FF',
    'done_surface':'#1E4030','done_text':'#A1E3BC',
    'logo_surface':'#F5F5F7','menu_selection_text':'#081827',
}

def colors(dark=False):
    return DARK if dark else LIGHT

def render_style(template,dark=False):
    result=template
    for role,value in colors(dark).items():result=result.replace('@'+role+'@',value)
    return result

def palette_colors(dark=False):
    t=colors(dark)
    return {
        'Window':t['window'],'WindowText':t['text'],'Base':t['surface'],
        'AlternateBase':t['alternate'],'Text':t['text'],'Button':t['surface'],
        'ButtonText':t['text'],'ToolTipBase':t['surface'],'ToolTipText':t['text'],
        'Highlight':t['selection'],'HighlightedText':t['text'],'BrightText':t['primary_text'],
        'Light':t['surface'],'Midlight':t['hover'],'Dark':t['border'],
        'Mid':t['divider'],'Shadow':t['disabled'],'Link':t['selection_text'],
        'LinkVisited':t['selection_text'],'PlaceholderText':t['placeholder'],
    }
