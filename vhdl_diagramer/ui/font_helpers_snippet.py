
    def edit_font(self, item: object):
        '''Opens a dialog to edit font settings for an Instance or Port.'''
        # Initial values
        family = getattr(item, 'font_family', "Arial")
        size = getattr(item, 'font_size', 10)
        bold = getattr(item, 'font_bold', False)
        italic = getattr(item, 'font_italic', False)
        
        new_settings = self.ask_font_settings(initial={'family': family, 'size': size, 'bold': bold, 'italic': italic})
        
        if new_settings:
            # Snapshot before change
            self.snapshot()
            
            # Update attributes
            item.font_family = new_settings['family']
            item.font_size = new_settings['size']
            item.font_bold = new_settings['bold']
            item.font_italic = new_settings['italic']
            
            self.draw() # Redraw

    def ask_font_settings(self, initial=None):
        if initial is None:
            initial = {'family': 'Arial', 'size': 10, 'bold': False, 'italic': False}
            
        dlg = tk.Toplevel(self)
        dlg.title("Edit Font")
        dlg.geometry("300x250")
        
        result = {}
        
        # Family
        tk.Label(dlg, text="Font Family:").pack(pady=(10, 0))
        families = ['Arial', 'Courier', 'Times', 'Helvetica', 'Verdana']
        family_var = tk.StringVar(value=initial['family'])
        if initial['family'] not in families:
            families.insert(0, initial['family'])
            
        cb_family = tk.OptionMenu(dlg, family_var, *families)
        cb_family.pack()
        
        # Size
        tk.Label(dlg, text="Font Size:").pack(pady=(10, 0))
        size_var = tk.IntVar(value=initial['size'])
        # Spinbox or entry
        sb_size = tk.Spinbox(dlg, from_=6, to=72, textvariable=size_var, width=5)
        sb_size.pack()
        
        # Style
        tk.Label(dlg, text="Style:").pack(pady=(10, 0))
        bold_var = tk.BooleanVar(value=initial['bold'])
        italic_var = tk.BooleanVar(value=initial['italic'])
        
        tk.Checkbutton(dlg, text="Bold", variable=bold_var).pack()
        tk.Checkbutton(dlg, text="Italic", variable=italic_var).pack()
        
        def on_ok():
            result['family'] = family_var.get()
            try:
                result['size'] = int(size_var.get())
            except ValueError:
                result['size'] = 10
            result['bold'] = bold_var.get()
            result['italic'] = italic_var.get()
            dlg.destroy()
            
        def on_cancel():
            result.clear()
            dlg.destroy()
            
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="OK", command=on_ok, width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_cancel, width=8).pack(side=tk.LEFT, padx=5)
        
        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        
        return result if result else None
