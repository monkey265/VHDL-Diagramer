# Instalation

In root of this project run following.
1. `pip install tk`
2. `pip install -e .`
3. `python -m vhdl_diagramer`




# TODO
- VHDL features:
  - [ ] Open keyword to be recognized
- [x] Add ability to move blocks
- Add right click menu:
  - [ ] Change color
  - [ ] Change size
  - [ ] Delete ports
  - [x] Add drag lock
  - [ ] Add pin lock


- [x]Undo/redo button
- [ ] Automatically find AXI and wrap them
- [ ] Add overlay around whole diagram with top level pins if they exist
- [ ] Export to various formats
- [ ] Render signals
- [ ] Render logical operations with nets
- [x] Split the code into packages to make it more maintainable
- [ ] Add suport for components
- [ ] Make a list of nets/ports/unused etc...
- [ ] tcl interface
- [ ] Support for verilog?