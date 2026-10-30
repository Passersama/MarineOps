"""Explicit semantic colors shared by the native stylesheet, palette and delegates."""
LIGHT = {
    'sidebar':'#EBEDF0','sidebar_selected':'#FFFFFF',
    'surface':'#FFFFFF','text':'#24262B','window':'#F5F5F7','divider':'#E5E5EA',
    'muted':'#5C6068','border':'#8491A1','hover':'#F0F3F8','hover_border':'#768798',
    'pressed':'#E7EDF5','disabled':'#8D9098','selection':'#EAF3FF','selection_text':'#0066CC',
    'selection_border':'#007AFF','menu_hover':'#E8EFF8','field_hover_border':'#BBC5D3',
    'field_hover':'#FAFBFD','field_disabled':'#858992','text_selection':'#D5E8FF',
    'focus':'#007AFF','tab_track':'#E9EAEE','tab_text':'#62656D','tab_hover':'#DFE2E8',
    'alternate':'#FAFAFC','header':'#60646C','scrollbar':'#939EAC','scrollbar_hover':'#6F7E90',
    'primary':'#0066D6','primary_hover':'#006BE0','primary_text':'#FFFFFF',
    'placeholder':'#65738A','error':'#B3261E','read_only':'#666970',
    'waiting_surface':'#FFF2D6','waiting_text':'#7A4B00',
    'onboard_surface':'#DFEDFF','onboard_text':'#174B87',
    'done_surface':'#E2F3E7','done_text':'#17603A',
    'logo_surface':'#F5F5F7','menu_selection_text':'#FFFFFF',
}
DARK = {
    'sidebar':'#10223E','sidebar_selected':'#254A78',
    'surface':'#192F4D','text':'#ECF2FC','window':'#0C1D35','divider':'#344D70',
    'muted':'#C0D0E7','border':'#708CAF','hover':'#294768','hover_border':'#A0BBDA',
    'pressed':'#315579','disabled':'#94A7BF','selection':'#294F7F','selection_text':'#ECF2FC',
    'selection_border':'#64A7F4','menu_hover':'#315A89','field_hover_border':'#7898BD',
    'field_hover':'#263F61','field_disabled':'#94A7BF','text_selection':'#315C92',
    'focus':'#64A7F4','tab_track':'#142741','tab_text':'#C0CEE2','tab_hover':'#2C496B',
    'alternate':'#1D3555','header':'#C0D0E7','scrollbar':'#7F9DBF','scrollbar_hover':'#AEC5DE',
    'primary':'#1764C6','primary_hover':'#2877D9','primary_text':'#FFFFFF',
    'placeholder':'#B1C3DC','error':'#FFB4AB','read_only':'#B2C4DE',
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
