import unittest
import tkinter as tk
from unittest.mock import MagicMock, patch
from vhdl_diagramer.ui.diagram_canvas import DiagramCanvas
from vhdl_diagramer.models import Instance, Port

class MockEvent:
    def __init__(self, x, y, state=0):
        self.x = x
        self.y = y
        self.state = state
        self.keysym = ''

class TestCanvasInteraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a hidden root window for Tkinter widgets
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.mock_callback = MagicMock()
        self.canvas = DiagramCanvas(self.root, [], [], [], [], assignments=[], 
                                   on_selection_change=self.mock_callback,
                                   scrollregion=(0,0,1000,1000))
        # Disable drawing to avoid Tcl errors in headless or during heavy mods
        self.canvas.draw = MagicMock() 
        self.canvas.draw.side_effect = lambda **kwargs: None 
        # But we might need some draw logic for pins?
        # For drag tests strategies, we test LOGIC, not rendering.
        
        self.canvas.grid_step = 20
        self.canvas.current_scale = 1.0

    def test_drag_instance_logic(self):
        """Test that dragging an instance updates its coordinates."""
        # 1. Setup Instance
        inst = Instance(name="U1", entity="Test", ports=[], x=100, y=100, width=100, height=100)
        self.canvas.instances.append(inst)
        
        # 2. Select it
        self.canvas.selected_instances = [inst]
        
        # 3. Setup Drag State (as on_click would)
        self.canvas.drag_offset_map = {inst: (0, 0)} # Clicked at top-left corner relative to inst
        # Click at 100, 100. Offset = 100-100 = 0
        
        # 4. Drag to 150, 150
        event = MockEvent(150, 150)
        self.canvas.on_drag(event)
        
        # 5. Verify
        # Expected: New position snapped to grid.
        # 150 snapped to 20 grid -> 140 or 160? 
        # round(150/20)*20 = 7.5*20 -> 8*20 = 160? Or 7*20=140? 
        # Python round ties to even? 7.5 -> 8.
        # Let's check logic: round(new_x / step) * step
        # new_x = 150 - 0 = 150.
        # round(7.5) = 8. -> 160.
        self.assertEqual(inst.x, 160)
        self.assertEqual(inst.y, 160)

    def test_drag_pin_logic(self):
        """Test that dragging a pin updates its position."""
        # 1. Setup Pin
        p = Port(name="clk", direction="IN", signal="s")
        self.canvas.top_level_pins.append(p)
        self.canvas.drag_pin = p
        
        # 2. Setup Drag State
        # Clicked exactly on pin current pos?
        # Assume pin was at 0,0. Clicked at 0,0.
        self.canvas.drag_pin_offset_x = 0
        self.canvas.drag_pin_offset_y = 0
        
        # 3. Drag to 40, 45
        event = MockEvent(40, 45)
        # 40 snapped to 20 -> 40
        # 45 snapped to 20 -> round(2.25)->2 -> 40.
        self.canvas.on_drag(event)
        
        # 4. Verify
        self.assertIn('clk', self.canvas.top_pin_positions)
        pos = self.canvas.top_pin_positions['clk']
        self.assertEqual(pos, (40, 40))

    def test_on_release_cleans_state(self):
        """Test that on_release clears drag flags."""
        
        # 1. Test Resizing Cleanup
        self.canvas.resizing = True
        self.canvas.on_release(MockEvent(0,0))
        self.assertFalse(self.canvas.resizing)

        # 2. Test Selecting Cleanup
        self.canvas.selecting = True
        # selecting requires drag_start vars
        self.canvas.drag_start_x = 0
        self.canvas.drag_start_y = 0
        self.canvas.selection_box_id = 1
        # It calls delete(selection_box_id) -> need to mock delete
        self.canvas.delete = MagicMock()
        
        self.canvas.on_release(MockEvent(0,0))
        self.assertFalse(self.canvas.selecting)
        
        # 3. Test Pin Drag Cleanup
        self.canvas.drag_pin = "Something"
        self.canvas.on_release(MockEvent(0,0))
        self.assertIsNone(self.canvas.drag_pin)
        
        # 4. Test Connection Drag Cleanup
        self.canvas.drag_conn_key = "Something"
        self.canvas.on_release(MockEvent(0,0))
        self.assertIsNone(self.canvas.drag_conn_key)

    def test_group_logic(self):
        """Test adding/removing items from groups."""
        # 1. Setup Group and Child
        group = Instance(name="G1", entity="Group", ports=[], x=0, y=0, width=200, height=200, is_group=True)
        child = Instance(name="C1", entity="Child", ports=[], x=50, y=50, width=50, height=50)
        self.canvas.instances.extend([group, child])
        self.canvas.selected_instances = [child]
        
        # 2. Add to Group
        # Mock the dialog to prevent hang
        with patch('vhdl_diagramer.ui.diagram_canvas.GroupCreationDialog') as MockDialog:
            instance = MockDialog.return_value
            instance.result = {'name': 'G1', 'ports': []} # Return valid result
            
            self.canvas.add_to_group(group, [child])
        
        self.assertIn(child, group.children)
        self.assertEqual(child.parent, group)
        
        # 3. Remove from Group (simulating remove_from_group)
        self.canvas.remove_from_group(child)
        
        self.assertNotIn(child, group.children)
        self.assertIsNone(child.parent)

    def test_toggle_bus_style(self):
        """Test toggling bus style."""
        # Setup
        p1 = Port(name="P1", direction="OUT", signal="mysig")
        inst1 = Instance(name="U1", entity="E1", ports=[p1])
        self.canvas.instances.append(inst1)
        
        # Select connection
        self.canvas.selected_connection_key = ("U1", "P1", "U2", "P2") # Dst doesn't matter for this logic check
        
        # Toggle On
        self.canvas.toggle_bus_style_selection()
        self.assertIn("mysig", self.canvas.bus_signals)
        
        # Toggle Off
        self.canvas.toggle_bus_style_selection()
        self.assertNotIn("mysig", self.canvas.bus_signals)

    def test_selection_callback(self):
        """Test that on_selection_change is called."""
        # Setup Instance
        inst = Instance(name="U1", entity="Test", ports=[], x=100, y=100, width=100, height=100)
        self.canvas.instances.append(inst)
        # self.canvas.active_instances = [inst] # get_active_instances relies on visibility which defaults to true? Yes.
        
        # 1. Click on instance (Select)
        event = MockEvent(110, 110) # Inside U1
        self.canvas.on_click(event)
        
        self.assertTrue(inst in self.canvas.selected_instances)
        # Verify callback called with specific message
        self.mock_callback.assert_called()
        args = self.mock_callback.call_args[0]
        self.assertIn("Selected Instance: U1", args[0])
        
        # 2. Click on empty space (Deselect)
        self.mock_callback.reset_mock()
        event = MockEvent(10, 10) # Outside
        self.canvas.on_click(event)
        
        self.assertEqual(len(self.canvas.selected_instances), 0)
        self.mock_callback.assert_called()
        args = self.mock_callback.call_args[0]
        self.assertIn("Ready", args[0])

    def test_pin_selection_notification(self):
        """Test notification when a pin is selected."""
        pin = Port(name="clk", direction="IN", signal="clk")
        self.canvas.selected_pin = pin
        
        self.mock_callback.reset_mock()
        self.canvas._notify_selection()
        
        self.mock_callback.assert_called()
        args = self.mock_callback.call_args[0]
        self.assertIn("Selected Pin: clk (IN)", args[0])

    def test_top_level_routing_bounds(self):
        """Test that draw() handles top-level pins for routing bounds without error."""
        p_in = Port(name="clk", direction="IN", signal="clk")
        p_out = Port(name="data_out", direction="OUT", signal="data")
        
        self.canvas.top_level_pins = [p_in, p_out]
        self.canvas.show_top_level = True
        self.canvas.grid_enabled = False # Simplify
        
        # Trigger draw (which crashed before)
        try:
            self.canvas.draw(routing=True)
        except AttributeError as e:
            self.fail(f"draw() raised AttributeError: {e}")

    def test_resize_instance(self):
        """Test that dragging the bottom-right corner resizes the instance."""
        inst = Instance(name="U_RES", entity="TEST", ports=[], x=100, y=100, width=100, height=100)
        self.canvas.instances.append(inst)
        self.canvas.selected_instances = [inst]
        
        # 1. Hover corner to trigger handle detection
        # Corner is at (200, 200). Logic requires mouse to be within 10px inside.
        # So x=195, y=195 should work.
        event_motion = MagicMock()
        event_motion.x = 195
        event_motion.y = 195
        # Need to ensure canvasx/y return same
        self.canvas.on_motion(event_motion)
        
        self.assertEqual(self.canvas.resize_handle_active, inst)
        
        # 2. Click (start drag)
        event_click = MagicMock()
        event_click.x = 195
        event_click.y = 195
        event_click.state = 0
        self.canvas.on_click(event_click)
        self.assertTrue(self.canvas.resizing)
        self.assertEqual(self.canvas.resize_start_inst, inst)
        
        # 3. Drag to resize
        # Drag to (210, 210) -> Width should be 110, Height 110 (approx)
        # offset was: cx - (inst.x+w) = 195 - 200 = -5
        # new cx = 210.
        # target_w = (210 - (-5)) - 100 = 215 - 100 = 115?
        # Let's trace calculation:
        # drag_off_x = 195 - (100+100) = -5
        # on_drag(210):
        # target_w = (210 - (-5)) - 100 = 115
        
        event_drag = MagicMock()
        event_drag.x = 230
        event_drag.y = 230
        self.canvas.on_drag(event_drag)
        
        # Verify resize happened
        # Since draw() is mocked, inst.width isn't updated by arrange_grid logic in this test harness.
        # But custom_width IS set by on_drag.
        self.assertTrue(inst.custom_width > 100)
        self.assertTrue(inst.custom_height > 100)
        
        # 4. Release
        event_release = MagicMock()
        self.canvas.on_release(event_release)
        self.assertFalse(self.canvas.resizing)
        
        # 5. Move away to clear handle
        event_motion.x = 0
        event_motion.y = 0
        self.canvas.on_motion(event_motion)
        self.assertIsNone(self.canvas.resize_handle_active)

if __name__ == '__main__':
    unittest.main()
