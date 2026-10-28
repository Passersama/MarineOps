"""Voyage overview: visibility, ordering and full labels through reflow."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication,QWidget
from cargo_track.route_layout import RouteButton,RouteLayout

class RouteLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.panel=QWidget();self.layout=RouteLayout(self.panel)
    def tearDown(self):self.panel.deleteLater();self.app.processEvents()
    def add(self,count):
        for i in range(count):self.layout.addWidget(RouteButton(f'{i+1} · BGP Vessel {i+1}'))
    def test_all_stops_fit_the_reported_wrapped_height(self):
        self.add(24);height=self.layout.heightForWidth(960);bounds=QRect(0,0,960,height);self.layout.setGeometry(bounds)
        self.assertGreater(len({self.layout.itemAt(i).geometry().y() for i in range(24)}),1)
        self.assertTrue(all(bounds.contains(self.layout.itemAt(i).geometry()) for i in range(24)))
    def test_reflow_retains_stop_order_and_selected_identity(self):
        self.add(13);buttons=[self.layout.itemAt(i).widget() for i in range(13)]
        buttons[-1].setCheckable(True);buttons[-1].setChecked(True)
        self.layout.setGeometry(QRect(0,0,960,self.layout.heightForWidth(960)))
        narrow=self.layout.heightForWidth(960);self.layout.setGeometry(QRect(0,0,1600,self.layout.heightForWidth(1600)))
        self.assertLessEqual(self.layout.heightForWidth(1600),narrow)
        ordered=sorted(buttons,key=lambda b:(b.y(),b.x()));self.assertEqual(buttons,ordered);self.assertTrue(buttons[-1].isChecked())
    def test_long_vessel_names_wrap_without_losing_characters(self):
        title='1 · '+('ExtremelyLongVesselName'*8)+' · Current';button=RouteButton(title);self.layout.addWidget(button)
        height=self.layout.heightForWidth(200);self.layout.setGeometry(QRect(0,0,200,height))
        self.assertIn('\n',button.text());self.assertEqual(''.join(title.split()),''.join(button.text().split()))
        self.assertLessEqual(button.width(),200);self.assertEqual(title,button.toolTip())
    def test_empty_route_has_no_placeholder_scroll_area(self):
        self.assertEqual(0,self.layout.count());self.assertEqual(0,self.layout.heightForWidth(960))
    def test_rebuilding_route_removes_every_old_item(self):
        self.add(13)
        while self.layout.count():self.layout.takeAt(0).widget().deleteLater()
        self.add(2);self.assertEqual(2,self.layout.count());self.assertEqual('2 · BGP Vessel 2',self.layout.itemAt(1).widget().full_title)
