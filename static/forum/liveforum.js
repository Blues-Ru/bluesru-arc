var ticket1 = "";
var ticket2 = "";
var ticket = "";

function ValidateCommentForm(theForm)
{
  if ($("#newPostSubject").val() == "")
  {
    alert("Вы забыли написать тему сообщения.");
    $("#newPostSubject").focus();
    return false;
  }

  if ($("#newPostText").val() == "")
  {
    if (!confirm("Отправить с пустым текстом сообщения?"))
    {
      $("#newPostText").focus();
      return false;
    }
  }
  $("#newPostTicket") = ticket;
  return true;
}

function OnCommentFormTimer()
{
  ticket = ticket1 + ticket2;
  //alert(ticket);
}

$(document).ready(function () {
  if (location.hash.substring(0, 5) == "#post")
  {
    var id = location.hash.substring(5);
    if (id)
      $("#bullet"+id).attr("src", "/forum/arrow.gif");
  }
  $("#postEmailBox").focus();
  $("#newPostSubject").focus();
  $("#newPostForm").submit(function() {
  
    //alert('c');
    if ($("#newPostSubject").val() == "")
    {
      alert("Вы забыли написать тему сообщения.");
      $("#newPostSubject").focus();
      return false;
    }

    if ($("#newPostText").val() == "")
    {
      if (!confirm("Отправить с пустым текстом сообщения?"))
      {
        $("#newPostText").focus();
        return false;
      }
    }
    $("#newPostTicket").val(ticket);
    return true;
  });
});
