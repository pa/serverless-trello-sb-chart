var Promise = window.TrelloPowerUp.Promise;
var t = window.TrelloPowerUp.iframe();

var selected_board_lists
var selected_cards_list
var sprint_start_day
var selected_lists = []
var selected_member_list = []
var selected_cards = []
var plugin_data = {}

// Changing size of Popup to match components inside it
t.render(function() {
  t.sizeTo('#content');
});

/////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////   Sprint Start Day Select    //////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Sprint Start Day whenever the page reloads
t.get('board', 'shared', 'sprint_start_day').then(function (sprintStartDay) {
  $('#sprintStartDaySelectEvents').val(sprintStartDay).change()
});

//Adding placeholder to the Sprint Start Day DropDown List
sprint_start_day = $("#sprintStartDaySelectEvents").select2({
  placeholder: "Select Sprint Start Day",
    minimumResultsForSearch: -1
});


//Selecting Sprint Start Day from DropDown List
$('#sprintStartDaySelectEvents').on('select2:select', function (e) {
  plugin_data['sprint_start_day'] = e.params.data.id
});


/////////////////////////////////////////////////////////////////////////////////////////////////////////

/////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////   Total Sprint Days   /////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Total Sprint Days whenever the page reloads
t.get('board', 'shared', 'total_sprint_days').then(function (totalSprintDays) {
  $('input[id="sprintDaysEvent"]').val(totalSprintDays)
});


//Setting Trello Env Vars for Total Sprint Days
$('input[id="sprintDaysEvent"]').change(function() {
  $('input[id="sprintDaysEvent"]').val($('input[id="sprintDaysEvent"]').val())
  plugin_data['total_sprint_days'] = $('input[id="sprintDaysEvent"]').val()
});

////////////////////////////////////////////////////////////////////////////////////////////////////////


/////////////////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////   Team Members Days Out of Office   //////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Team Members Days Out of Office  whenever the page reloads
t.get('board', 'shared', 'team_members_days_ooo').then(function (teamMembersDaysOOO) {
  $('input[id="teamMembersDaysOOOEvent"]').val(teamMembersDaysOOO)
});


//Setting Trello Env Vars for Team Members Days Out of Office 
$('input[id="teamMembersDaysOOOEvent"]').change(function() {
  $('input[id="teamMembersDaysOOOEvent"]').val($('input[id="teamMembersDaysOOOEvent"]').val())
  plugin_data['team_members_days_ooo'] = $('input[id="teamMembersDaysOOOEvent"]').val()
});

////////////////////////////////////////////////////////////////////////////////////////////////////////

/////////////////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////   Show/Hide Team Size on Chart   /////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Show/Hide Team Size on Chart whenever the page reloads
t.get('board', 'shared', 'is_show_team_size').then(function (teamMembersDaysOOO) {
  $("#showTeamSizeOnChart").prop('checked', JSON.parse(teamMembersDaysOOO.toLowerCase()));
});


//Setting Trello Env Vars for Show/Hide Team Size on Chart
$("#showTeamSizeOnChart").on('change', function() {
  if ($(this).is(':checked')) {
    $(this).attr('value', 'True');
  } else {
    $(this).attr('value', 'False');
  }
  plugin_data['is_show_team_size'] = $('#showTeamSizeOnChart').val()
});

////////////////////////////////////////////////////////////////////////////////////////////////////////


/////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////   Stories/Defects and Tasks Remaining List   //////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Adding Board Lists to DropDown options
t.lists('all')
    .then(function (board) {
      for (var list_index in board) {
        if( !board[list_index]['name'].match(/Done/g))
           {
             var newOption = new Option(board[list_index].name, board[list_index].id, false, false);
             $('#selectEvents').append(newOption).trigger('change');
           }
      }
});

//Setting the selected Board Lists in the DropDown Field
t.get('board', 'shared', 'selected_list')
    .then(function (selectedList) {
      selected_board_lists.val(Object.values(selectedList)).trigger("change");
});

//Adding placeholder to the DropDown List
selected_board_lists = $("#selectEvents").select2({
    placeholder: "Choose Lists to be monitored",
});

//Selecting Board Lists from DropDown List
$('#selectEvents').on('select2:select', function (e) {
  selected_lists = $("#selectEvents").select2("val")
  selected_lists = selected_lists.filter(function(v, i, self) {
    // It returns the index of the first
    // instance of each value
    return i == self.indexOf(v);
  });
  plugin_data['selected_list'] = selected_lists
});

//Un-Selecting Board Lists from DropDown List
$('#selectEvents').on('select2:unselect', function (e) {
  selected_lists = $("#selectEvents").select2("val")
  plugin_data['selected_list'] = selected_lists
});

/////////////////////////////////////////////////////////////////////////////////////////////////////////


/////////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////   Pick the Done List   //////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Done List whenever the page reloads
t.get('board', 'shared', 'selected_done_list').then(function (lists) {
  $('#doneCardEvents').val(lists).change()
});

//Adding Done Lists to DropDown options
t.lists('all')
    .then(function (lists) {

      for (var list_index in lists) {
        if( lists[list_index]['name'].match(/Done/g))
           {
             var newOption = new Option(lists[list_index].name, lists[list_index].id, false, false);
             $('#doneCardEvents').append(newOption).trigger('change');
           }
      }
});

//Adding placeholder to the DropDown List
selected_cards_list = $("#doneCardEvents").select2({
    placeholder: "Pick the Done List",
});

//Picking Done List from DropDown List
$('#doneCardEvents').on('select2:select', function (e) {
  plugin_data['selected_done_list'] = e.params.data.id
});

/////////////////////////////////////////////////////////////////////////////////////////////////////////


/////////////////////////////////////////////////////////////////////////////////////////////////////////
///////////////////////////////////   Team Members List   ///////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Addind Team Members Lists to DropDown options
t.board('members')
  .then(function (member) {
  for (var member_list_index in member['members']) {
    var teamMemberOption = new Option(member['members'][member_list_index].fullName, member['members'][member_list_index].fullName, false, false);
    $('#teamMemberListSelectEvents').append(teamMemberOption).trigger('change');
  }
});

//Setting the selected Team Members in the DropDown Field
t.get('board', 'shared', 'team_member_list')
    .then(function (teamMemberList) {
      selected_member_list.val(Object.values(teamMemberList)).trigger("change");
});


//Adding placeholder to the DropDown List
selected_member_list = $("#teamMemberListSelectEvents").select2({
    placeholder: "Select Team Members",
});

//Selecting Team Members from DropDown List
$('#teamMemberListSelectEvents').on('select2:select', function (e) {
  selected_member_list = $("#teamMemberListSelectEvents").select2("val")
  selected_member_list = selected_member_list.filter(function(v, i, self) {
    // It returns the index of the first
    // instance of each value
    return i == self.indexOf(v);
  });
  plugin_data['team_member_list'] = selected_member_list
});

//Un-Selecting Team Members from DropDown List
$('#teamMemberListSelectEvents').on('select2:unselect', function (e) {
  selected_member_list = $("#teamMemberListSelectEvents").select2("val")
  plugin_data['team_member_list'] = selected_member_list
});

////////////////////////////////////////////////////////////////////////////////////////////////////////////


/////////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////   Pick the Card to Attach Sprint Burndown Chart   //////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////

//Setting Card whenever the page reloads
t.get('board', 'shared', 'selected_card_for_attachment').then(function (card) {
  $('#selectCardEvents').val(card).change()
});

//Adding Card Lists to DropDown options
t.cards('all')
    .then(function (card) {

      for (var list_index in card) {
             var newOption = new Option(card[list_index].name, card[list_index].id, false, false);
             $('#selectCardEvents').append(newOption).trigger('change');
      }
});

//Adding placeholder to the DropDown List
selected_cards_list = $("#selectCardEvents").select2({
    placeholder: "Pick the Card to attach",
});

//Picking Card from DropDown List
$('#selectCardEvents').on('select2:select', function (e) {
  plugin_data['selected_card_for_attachment'] = e.params.data.id
});

/////////////////////////////////////////////////////////////////////////////////////////////////////////


///////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////   Save Configuration    //////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////////
document.getElementById('save-btn').addEventListener('click', function(event){

      t.set('board', 'shared', plugin_data)

      var delayInMilliseconds = 1000; //1 second

      setTimeout(function() {
        t.closePopup();
        t.alert({
          message: 'Configuration Saved Successfully',
          duration: 2,
          display: 'success'
        });
      }, delayInMilliseconds);
});

///////////////////////////////////////////////////////////////////////////////////


///////////////////////////////////////////////////////////////////////////////////
//////////////////////////////   Clear Configuration    ///////////////////////////
///////////////////////////////////////////////////////////////////////////////////
document.getElementById('clear-btn').addEventListener('click', function(event){
      return t.get('board', 'shared')
        .then(function (data) {
        t.remove('board', 'shared', Object.keys(data));
        location.reload();
        });
});

///////////////////////////////////////////////////////////////////////////////////
