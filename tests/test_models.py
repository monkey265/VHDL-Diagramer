import unittest
from vhdl_diagramer.models import Instance, Port

class TestModels(unittest.TestCase):

    def test_port_creation(self):
        p = Port(name="clk", direction="IN", signal="clk_sig")
        self.assertEqual(p.name, "clk")
        self.assertEqual(p.direction, "IN")
        self.assertEqual(p.signal, "clk_sig")
        # Defaults
        self.assertEqual(p.font_family, "Arial")

    def test_instance_creation(self):
        p1 = Port(name="in1", direction="IN", signal="s1")
        inst = Instance(name="U1", entity="MyEntity", ports=[p1])
        
        self.assertEqual(inst.name, "U1")
        self.assertEqual(inst.entity, "MyEntity")
        self.assertEqual(len(inst.ports), 1)
        self.assertEqual(inst.x, 0)
        self.assertFalse(inst.locked) # Critical check from previous bugs

    def test_instance_locked_attribute(self):
        inst = Instance(name="L1", entity="LockedEntity", ports=[], locked=True)
        self.assertTrue(inst.locked)
        
    def test_instance_group_defaults(self):
        inst = Instance(name="G1", entity="Group", ports=[])
        self.assertFalse(inst.is_group)
        self.assertFalse(inst.collapsed)
        self.assertEqual(inst.children, [])

if __name__ == '__main__':
    unittest.main()
