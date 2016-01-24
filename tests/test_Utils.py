from mc.core.utils import set_position, get_insert_index, percent_to_float
from tests.MpfMcTestCase import MpfMcTestCase


class TestUtils(MpfMcTestCase):
    def get_machine_path(self):
        return 'tests/machine_files/utils'

    def get_config_file(self):
        return 'test_utils.yaml'

    def test_set_position(self):
        parent_w = 100
        parent_h = 100
        w = 10
        h = 10
        x = None
        y = None
        anchor_x = None
        anchor_y = None

        # For all these tests, the widget is 10x10, and the resulting x,y
        # positions represent the lower left corner of the widget.

        # No anchor set, widget should be centered in the parent. Parent is
        # 100x100, widget is 10x10, so center of the parent is 50, 50, and
        # lower left corner of the widget is 45, 45

        # test with all defaults

        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (45, 45))

        # test anchors

        anchor_x = 'left'
        anchor_y = 'bottom'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (50, 50))

        anchor_x = 'middle'
        anchor_y = 'middle'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (45, 45))

        anchor_x = 'center'
        anchor_y = 'center'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (45, 45))

        anchor_x = 'right'
        anchor_y = 'top'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (40, 40))

        # test positive x, y numbers

        x = 10
        y = 10

        anchor_x = 'left'
        anchor_y = 'bottom'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (10, 10))

        anchor_x = 'middle'
        anchor_y = 'middle'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (5, 5))

        anchor_x = 'center'
        anchor_y = 'center'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (5, 5))

        anchor_x = 'right'
        anchor_y = 'top'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (0, 0))

        # test negative x, y numbers

        x = -10
        y = -10
        anchor_x = None
        anchor_y = None

        anchor_x = 'left'
        anchor_y = 'bottom'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-10, -10))

        anchor_x = 'middle'
        anchor_y = 'middle'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-15, -15))

        anchor_x = 'center'
        anchor_y = 'center'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-15, -15))

        anchor_x = 'right'
        anchor_y = 'top'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-20, -20))

        # test positive percentages

        x = '80%'
        y = '20%'

        anchor_x = 'left'
        anchor_y = 'bottom'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (80, 20))

        anchor_x = 'middle'
        anchor_y = 'middle'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (75, 15))

        anchor_x = 'center'
        anchor_y = 'center'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (75, 15))

        anchor_x = 'right'
        anchor_y = 'top'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (70, 10))

        # test negative percentages (dunno how useful these are, but they work)

        x = '-80%'
        y = '-20%'

        anchor_x = 'left'
        anchor_y = 'bottom'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-80, -20))

        anchor_x = 'middle'
        anchor_y = 'middle'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-85, -25))

        anchor_x = 'center'
        anchor_y = 'center'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-85, -25))

        anchor_x = 'right'
        anchor_y = 'top'
        res_x, res_y = set_position(parent_w, parent_h, w, h, x, y,
                                    anchor_x, anchor_y)
        self.assertEqual((res_x, res_y), (-90, -30))

    def test_percent_to_float(self):
        num = 1
        total = 1
        self.assertEqual(percent_to_float(num, total), 1.0)

        num = 1
        total = 2
        self.assertEqual(percent_to_float(num, total), 1.0)

        num = 0
        total = 2
        self.assertEqual(percent_to_float(num, total), 0.0)

        num = '1'
        total = 1
        self.assertEqual(percent_to_float(num, total), 1.0)

        num = '1'
        total = 2
        self.assertEqual(percent_to_float(num, total), 1.0)

        num = '0'
        total = 2
        self.assertEqual(percent_to_float(num, total), 0.0)

        num = '100%'
        total = 1
        self.assertEqual(percent_to_float(num, total), 1.0)

        num = '100%'
        total = 2
        self.assertEqual(percent_to_float(num, total), 2.0)

        num = '0%'
        total = 2
        self.assertEqual(percent_to_float(num, total), 0.0)

        num = '25%'
        total = 800
        self.assertEqual(percent_to_float(num, total), 200.0)

        num = '200%'
        total = 1
        self.assertEqual(percent_to_float(num, total), 2.0)

    def test_get_insert_index(self):
        self.mc.events.post('show_slide1')
        self.advance_time()

        index = get_insert_index(75, self.mc.targets['default'].current_slide)
        self.assertEqual(index, 2)