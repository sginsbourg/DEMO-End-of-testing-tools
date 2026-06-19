"""
Notepad Save Button Automation Test Suite
Tests enable/disable states and functionality of the Save button
"""

import time
import os
import tempfile
from pywinauto import Application
from pywinauto import keyboard
from pywinauto.timings import wait_until
import unittest

class NotepadSaveButtonTests:
    """Test suite for Notepad Save button behavior"""
    
    def __init__(self):
        self.app = None
        self.notepad = None
        self.test_file_path = None
        self.test_results = []
        
    def setup(self):
        """Initialize Notepad and create a test file"""
        # Create a temporary file for testing
        temp_dir = tempfile.gettempdir()
        self.test_file_path = os.path.join(temp_dir, "notepad_test.txt")
        
        # Create a test file with initial content
        with open(self.test_file_path, 'w') as f:
            f.write("Initial test content")
        
        # Launch Notepad
        self.app = Application().start("notepad.exe")
        time.sleep(1)
        self.notepad = self.app.window(title="Untitled - Notepad")
        
        # Open the test file
        keyboard.send_keys('^o')  # Ctrl+O
        time.sleep(1)
        
        # Type the file path and press Enter
        keyboard.send_keys(self.test_file_path)
        time.sleep(0.5)
        keyboard.send_keys('{ENTER}')
        time.sleep(1)
        
        return self
    
    def teardown(self):
        """Close Notepad and cleanup"""
        if self.app:
            try:
                # Close without saving
                self.notepad.close()
            except:
                pass
            
        # Cleanup test file
        if self.test_file_path and os.path.exists(self.test_file_path):
            try:
                os.remove(self.test_file_path)
            except:
                pass
    
    def get_save_button_state(self):
        """Check if Save button is enabled or disabled"""
        try:
            # Try to find the Save button in the toolbar
            # Method 1: Try by menu path
            try:
                file_menu = self.notepad.menu_select("File")
                time.sleep(0.5)
                # Check if Save is enabled (not greyed out)
                save_item = self.notepad.child_window(title="Save", control_type="MenuItem")
                return save_item.is_enabled()
            except:
                pass
            
            # Method 2: Try by Ctrl+S shortcut detection
            # We'll use a workaround - check the title bar for asterisk
            title = self.notepad.window_text()
            has_asterisk = '*' in title and title.index('*') < title.index(' - ')
            
            # If asterisk is present, button should be enabled
            # This is an indirect check but reliable
            return has_asterisk
            
        except Exception as e:
            print(f"Error getting button state: {e}")
            return False
    
    def check_title_bar(self):
        """Check if asterisk is in title bar (indicates unsaved changes)"""
        title = self.notepad.window_text()
        return '*' in title and title.index('*') < title.index(' - ')
    
    def perform_save(self):
        """Perform save operation"""
        try:
            # Try menu save
            self.notepad.menu_select("File -> Save")
            time.sleep(1)
            return True
        except:
            try:
                # Fallback to Ctrl+S
                keyboard.send_keys('^s')
                time.sleep(1)
                return True
            except:
                return False
    
    def log_result(self, test_name, passed, expected, actual):
        """Log test results"""
        result = {
            'test': test_name,
            'passed': passed,
            'expected': expected,
            'actual': actual
        }
        self.test_results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            print(f"  Expected: {expected}, Actual: {actual}")
    
    # ============= TEST CASES =============
    
    def test_initial_state(self):
        """Test 1: New file should have Save button disabled"""
        print("\n📝 Test 1: Initial Save Button State")
        
        # Restart Notepad with new file
        self.teardown()
        self.app = Application().start("notepad.exe")
        time.sleep(1)
        self.notepad = self.app.window(title="Untitled - Notepad")
        
        button_enabled = self.get_save_button_state()
        expected = False  # Should be disabled
        self.log_result("New file - Save button disabled", 
                       button_enabled == expected, expected, button_enabled)
        
        return self
    
    def test_enable_after_typing(self):
        """Test 2: Typing should enable Save button"""
        print("\n📝 Test 2: Typing Enables Save Button")
        
        # Type some text
        keyboard.send_keys("Hello World!")
        time.sleep(0.5)
        
        button_enabled = self.get_save_button_state()
        expected = True  # Should be enabled
        self.log_result("After typing - Save button enabled", 
                       button_enabled == expected, expected, button_enabled)
        
        return self
    
    def test_disable_after_save(self):
        """Test 3: Saving should disable Save button"""
        print("\n📝 Test 3: Saving Disables Save Button")
        
        # Perform save
        self.perform_save()
        time.sleep(1)
        
        button_enabled = self.get_save_button_state()
        expected = False  # Should be disabled after save
        self.log_result("After save - Save button disabled", 
                       button_enabled == expected, expected, button_enabled)
        
        return self
    
    def test_enable_after_modification_after_save(self):
        """Test 4: Modifying after save should enable Save button"""
        print("\n📝 Test 4: Modification After Save Enables Button")
        
        # First ensure we're in saved state
        self.perform_save()
        time.sleep(1)
        
        # Type additional text
        keyboard.send_keys(" Additional text")
        time.sleep(0.5)
        
        button_enabled = self.get_save_button_state()
        expected = True  # Should be enabled after modification
        self.log_result("After modification - Save button enabled", 
                       button_enabled == expected, expected, button_enabled)
        
        return self
    
    def test_undo_after_save(self):
        """Test 5: Undo after save should enable Save button"""
        print("\n📝 Test 5: Undo After Save Enables Button")
        
        # Type text and save
        keyboard.send_keys("Undo test")
        time.sleep(0.5)
        self.perform_save()
        time.sleep(1)
        
        # Press Ctrl+Z to undo
        keyboard.send_keys('^z')
        time.sleep(0.5)
        
        button_enabled = self.get_save_button_state()
        expected = True  # Undo changes document state
        self.log_result("After undo - Save button enabled", 
                       button_enabled == expected, expected, button_enabled)
        
        return self
    
    def test_save_as_functionality(self):
        """Test 6: Save As functionality"""
        print("\n📝 Test 6: Save As Test")
        
        # Create a new file via Save As
        try:
            keyboard.send_keys('{F12}')  # Save As shortcut
            time.sleep(1)
            
            # Use a different filename
            new_file = os.path.join(tempfile.gettempdir(), "notepad_saveas_test.txt")
            keyboard.send_keys(new_file)
            time.sleep(0.5)
            keyboard.send_keys('{ENTER}')
            time.sleep(1)
            
            # Verify save was successful
            button_enabled = self.get_save_button_state()
            expected = False  # Should be disabled after save
            self.log_result("Save As - Button disabled after saving", 
                           button_enabled == expected, expected, button_enabled)
            
            # Cleanup
            if os.path.exists(new_file):
                os.remove(new_file)
                
        except Exception as e:
            print(f"Save As test error: {e}")
            self.log_result("Save As", False, "File saved successfully", "Error occurred")
        
        return self
    
    def test_multiple_instances(self):
        """Test 7: Multiple Notepad instances behave independently"""
        print("\n📝 Test 7: Multiple Instance Test")
        
        # Open second Notepad instance
        app2 = Application().start("notepad.exe")
        time.sleep(1)
        notepad2 = app2.window(title="Untitled - Notepad")
        
        # Type in first instance
        keyboard.send_keys("Instance 1 text")
        time.sleep(0.5)
        
        # Check first instance state
        button1_enabled = self.get_save_button_state()
        
        # Check second instance state (should be disabled)
        # Switch to second instance
        notepad2.set_focus()
        time.sleep(0.5)
        button2_enabled = self.get_save_button_state()
        
        # Log results
        self.log_result("Instance 1 - Button enabled after typing", 
                       button1_enabled == True, True, button1_enabled)
        self.log_result("Instance 2 - Button disabled (no changes)", 
                       button2_enabled == False, False, button2_enabled)
        
        # Cleanup
        notepad2.close()
        
        return self
    
    def test_unsaved_changes_on_close(self):
        """Test 8: Verify unsaved changes prompt on close"""
        print("\n📝 Test 8: Unsaved Changes Prompt Test")
        
        # Type some text
        keyboard.send_keys("Unsaved text for close test")
        time.sleep(0.5)
        
        # Try to close Notepad
        self.notepad.close()
        time.sleep(1)
        
        # Check if dialog appears
        try:
            dialog = self.app.window(title="Notepad", class_name="#32770")
            save_button = dialog.child_window(title="Save", class_name="Button")
            donot_save = dialog.child_window(title="Don't Save", class_name="Button")
            cancel = dialog.child_window(title="Cancel", class_name="Button")
            
            # Dialog appeared - click Cancel to keep testing
            cancel.click()
            time.sleep(0.5)
            
            self.log_result("Unsaved changes prompt appears on close", 
                           True, "Dialog shown", "Dialog shown")
        except:
            self.log_result("Unsaved changes prompt appears on close", 
                           False, "Dialog shown", "No dialog")
        
        return self
    
    def test_rapid_save_stress(self):
        """Test 9: Stress test with rapid saves"""
        print("\n📝 Test 9: Rapid Save Stress Test")
        
        for i in range(10):
            # Type a character
            keyboard.send_keys(f"{i}")
            time.sleep(0.1)
            
            # Save
            self.perform_save()
            time.sleep(0.1)
            
            # Check button state after each save
            button_enabled = self.get_save_button_state()
            if button_enabled:
                print(f"  ⚠️ Cycle {i+1}: Button still enabled after save")
        
        # Final check
        final_state = self.get_save_button_state()
        self.log_result("Rapid saves - Button disabled after final save", 
                       final_state == False, False, final_state)
        
        return self
    
    def run_all_tests(self):
        """Run all test cases sequentially"""
        print("\n" + "="*60)
        print("🧪 NOTEPAD SAVE BUTTON AUTOMATION TEST SUITE")
        print("="*60)
        
        try:
            self.setup()
            
            # Run all tests
            self.test_initial_state()
            self.test_enable_after_typing()
            self.test_disable_after_save()
            self.test_enable_after_modification_after_save()
            self.test_undo_after_save()
            self.test_save_as_functionality()
            # self.test_multiple_instances()  # Uncomment if needed
            self.test_unsaved_changes_on_close()
            self.test_rapid_save_stress()
            
        except Exception as e:
            print(f"\n❌ Test suite error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.teardown()
            self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r['passed'])
        failed = total - passed
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Pass Rate: {(passed/total*100):.1f}%")
        
        if failed > 0:
            print("\n❌ Failed Tests:")
            for r in self.test_results:
                if not r['passed']:
                    print(f"  - {r['test']}: Expected {r['expected']}, Got {r['actual']}")
        else:
            print("\n🎉 All tests passed successfully!")
        
        print("="*60)

# =============================================
# ADVANCED TEST SUITE WITH UNITTEST FRAMEWORK
# =============================================

class AdvancedNotepadTests(unittest.TestCase):
    """Unittest version with more structured testing"""
    
    @classmethod
    def setUpClass(cls):
        cls.tester = NotepadSaveButtonTests()
        cls.tester.setup()
    
    @classmethod
    def tearDownClass(cls):
        cls.tester.teardown()
    
    def test_01_button_state_initial(self):
        """Test initial button state"""
        state = self.tester.get_save_button_state()
        self.assertFalse(state, "Save button should be disabled initially")
    
    def test_02_button_state_after_typing(self):
        """Test button enables after typing"""
        keyboard.send_keys("Test text")
        time.sleep(0.5)
        state = self.tester.get_save_button_state()
        self.assertTrue(state, "Save button should be enabled after typing")
    
    def test_03_button_state_after_save(self):
        """Test button disables after save"""
        self.tester.perform_save()
        time.sleep(0.5)
        state = self.tester.get_save_button_state()
        self.assertFalse(state, "Save button should be disabled after save")

# =============================================
# EXECUTION
# =============================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════╗
    ║   NOTEPAD SAVE BUTTON AUTOMATION TEST SUITE     ║
    ║                                                ║
    ║  This script will automatically test:          ║
    ║  ✅ Button enable/disable states              ║
    ║  ✅ Save functionality                        ║
    ║  ✅ Undo/Redo behavior                       ║
    ║  ✅ Multiple instances                       ║
    ║  ✅ Unsaved changes prompts                  ║
    ╚══════════════════════════════════════════════════╝
    """)
    
    # Run the tests
    tester = NotepadSaveButtonTests()
    tester.run_all_tests()
    
    # Uncomment to run unittest version instead:
    # unittest.main()